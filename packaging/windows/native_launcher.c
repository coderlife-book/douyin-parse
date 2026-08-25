#define UNICODE
#define _UNICODE

#include <windows.h>
#include <wchar.h>

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR command_line, int show_command) {
    wchar_t executable[MAX_PATH];
    wchar_t root[MAX_PATH];
    wchar_t python[MAX_PATH];
    wchar_t script[MAX_PATH];
    wchar_t child_command[MAX_PATH * 3];
    STARTUPINFOW startup = {0};
    PROCESS_INFORMATION process = {0};
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION job_limits = {0};
    HANDLE job;
    DWORD exit_code = 1;
    wchar_t *separator;

    (void)instance;
    (void)previous;
    (void)command_line;
    (void)show_command;

    if (!GetModuleFileNameW(NULL, executable, MAX_PATH)) {
        MessageBoxW(NULL, L"Cannot locate the launcher.", L"Douyin Video Tool", MB_ICONERROR);
        return 1;
    }
    wcscpy_s(root, MAX_PATH, executable);
    separator = wcsrchr(root, L'\\');
    if (!separator) {
        return 1;
    }
    *separator = L'\0';

    SetCurrentDirectoryW(root);
    SetEnvironmentVariableW(L"DOUYIN_PARSE_ROOT", root);
    SetEnvironmentVariableW(L"PYTHONUTF8", L"1");

    swprintf_s(python, MAX_PATH, L"%ls\\runtime\\python\\python.exe", root);
    swprintf_s(script, MAX_PATH, L"%ls\\app\\desktop_launcher.py", root);
    swprintf_s(child_command, MAX_PATH * 3, L"\"%ls\" -s \"%ls\"", python, script);

    startup.cb = sizeof(startup);
    if (!CreateProcessW(
            python,
            child_command,
            NULL,
            NULL,
            FALSE,
            CREATE_NEW_CONSOLE | CREATE_SUSPENDED,
            NULL,
            root,
            &startup,
            &process)) {
        MessageBoxW(NULL, L"Cannot start the bundled Python runtime.", L"Douyin Video Tool", MB_ICONERROR);
        return 1;
    }

    job = CreateJobObjectW(NULL, NULL);
    if (job) {
        job_limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        SetInformationJobObject(
            job,
            JobObjectExtendedLimitInformation,
            &job_limits,
            sizeof(job_limits)
        );
        AssignProcessToJobObject(job, process.hProcess);
    }

    ResumeThread(process.hThread);
    WaitForSingleObject(process.hProcess, INFINITE);
    GetExitCodeProcess(process.hProcess, &exit_code);

    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    if (job) {
        CloseHandle(job);
    }
    return (int)exit_code;
}
