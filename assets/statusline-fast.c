/* statusline 热路径（Windows，编译产物 statusline-fast.exe）
 *
 * 为什么存在：kimi-code 给 [status_line] 命令的预算只有 300ms，超时 taskkill /T /F 并丢弃结果。
 * 这台机器上 cmd(≈40ms) + 解释器启动(≈90-150ms) + 脚本自身(≈80ms) 空闲约 240ms、机器忙时
 * 400ms+，同步跑 Python 必然间歇性超时 -> footer 回落内置布局。
 *
 * 本程序只做三件事（实测 ~10ms）：
 *   1. 把 stdin 的 JSON 快照按「会话键」（当前目录叶子名）存成 payload_<key>.json；
 *   2. 把守护进程预渲染好的 line_<key>.txt 原样打印到 stdout；
 *   3. 守护进程心跳过期（>5 秒）时悄悄拉起 pythonw statusline-daemon.pyw
 *      （bInheritHandles=FALSE + DETACHED_PROCESS：不继承 runner 的管道，cmd 不等待）。
 * 真正的计算在 statusline-daemon.pyw 里，不受 300ms 限制。
 */
#include <windows.h>
#include <stdio.h>
#include <string.h>

#define BS 92
#define MAXBUF (1 << 20)
#define HEARTBEAT_MAX_AGE_S 5

static void leaf_key(char *out, size_t cap) {
    char cwd[MAX_PATH];
    char *p;
    DWORD len;
    size_t i, k = 0;
    if (!GetCurrentDirectoryA(MAX_PATH, cwd)) {
        _snprintf(out, cap, "default");
        out[cap - 1] = 0;
        return;
    }
    len = (DWORD)strlen(cwd);
    while (len > 0 && (cwd[len - 1] == BS || cwd[len - 1] == '/')) cwd[--len] = 0;
    p = cwd;
    for (i = 0; i < len; i++) {
        if (cwd[i] == BS || cwd[i] == '/') p = cwd + i + 1;
    }
    for (i = 0; p[i] && k + 1 < cap; i++) {
        char c = p[i];
        if (c == ':' || c == '*' || c == '?' || c == '"' || c == '<' || c == '>' || c == '|' || c == BS) c = '_';
        out[k++] = c;
    }
    if (k == 0) {
        _snprintf(out, cap, "default");
        out[cap - 1] = 0;
        return;
    }
    out[k] = 0;
}

static int file_equals(const char *path, const char *data, size_t len) {
    static char buf[1 << 16];
    FILE *f = fopen(path, "rb");
    size_t r;
    if (!f) return 0;
    r = fread(buf, 1, sizeof buf, f);
    fclose(f);
    return r == len && memcmp(buf, data, len) == 0;
}

static void write_bytes(const char *path, const char *data, size_t len) {
    FILE *f = fopen(path, "wb");
    if (!f) return;
    fwrite(data, 1, len, f);
    fclose(f);
}

static int heartbeat_fresh(const char *path) {
    WIN32_FILE_ATTRIBUTE_DATA fad;
    FILETIME now;
    ULONGLONG a, b;
    if (!GetFileAttributesExA(path, GetFileExInfoStandard, &fad)) return 0;
    GetSystemTimeAsFileTime(&now);
    a = ((ULONGLONG)fad.ftLastWriteTime.dwHighDateTime << 32) | fad.ftLastWriteTime.dwLowDateTime;
    b = ((ULONGLONG)now.dwHighDateTime << 32) | now.dwLowDateTime;
    if (b <= a) return 1;
    return (b - a) < (ULONGLONG)HEARTBEAT_MAX_AGE_S * 10000000ULL;
}

static void spawn_daemon(const char *kh) {
    char cmd[MAX_PATH * 3];
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    _snprintf(cmd, sizeof cmd, "pythonw %s/statusline-daemon.pyw", kh);
    cmd[sizeof cmd - 1] = 0;
    ZeroMemory(&si, sizeof si);
    si.cb = sizeof si;
    ZeroMemory(&pi, sizeof pi);
    if (CreateProcessA(NULL, cmd, NULL, NULL, FALSE,
                       DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
                       NULL, NULL, &si, &pi)) {
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
    }
}

int main(void) {
    static char buf[MAXBUF];
    char kh[MAX_PATH] = "", st[MAX_PATH * 2], key[160];
    char payload[MAX_PATH * 3], line[MAX_PATH * 3], hb[MAX_PATH * 3];
    size_t len = 0;
    DWORD got;
    FILE *f;

    if (!GetEnvironmentVariableA("KIMI_CODE_HOME", kh, sizeof kh)) {
        if (!GetEnvironmentVariableA("USERPROFILE", kh, sizeof kh)) return 0;
        strncat(kh, "/.kimi-code", sizeof kh - strlen(kh) - 1);
    }
    _snprintf(st, sizeof st, "%s/statusline", kh);
    st[sizeof st - 1] = 0;
    leaf_key(key, sizeof key);
    _snprintf(payload, sizeof payload, "%s/payload_%s.json", st, key);
    _snprintf(line, sizeof line, "%s/line_%s.txt", st, key);
    _snprintf(hb, sizeof hb, "%s/daemon.heartbeat", st);
    payload[sizeof payload - 1] = 0;
    line[sizeof line - 1] = 0;
    hb[sizeof hb - 1] = 0;

    while (len + 1 < sizeof buf) {
        if (!ReadFile(GetStdHandle(STD_INPUT_HANDLE), buf + len, (DWORD)(sizeof buf - 1 - len), &got, NULL) || got == 0) break;
        len += got;
    }
    buf[len] = 0;

    if (len > 0 && !file_equals(payload, buf, len)) write_bytes(payload, buf, len);

    f = fopen(line, "rb");
    if (f) {
        size_t r = fread(buf, 1, sizeof buf, f);
        fclose(f);
        if (r > 0) {
            fwrite(buf, 1, r, stdout);
            if (buf[r - 1] != '\n') fputc('\n', stdout);
        }
    }
    fflush(stdout);

    if (!heartbeat_fresh(hb)) spawn_daemon(kh);
    return 0;
}
