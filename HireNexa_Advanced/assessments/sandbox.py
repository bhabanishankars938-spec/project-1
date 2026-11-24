import os
import re
import sys
import time
import shutil
import tempfile
import subprocess
from typing import Dict, Any, List, Optional, Tuple


# ==============================================================================
# SECURITY RULE SETS & PROHIBITED TOKEN DETECTION
# ==============================================================================

PROHIBITED_PATTERNS = {
    "python": [
        r"\bos\.(system|popen|spawn|exec|remove|unlink|rmdir)\b",
        r"\bsubprocess\b",
        r"\bshutil\.(rmtree|move|copy)\b",
        r"\bimport\s+socket\b",
        r"\bfrom\s+socket\b",
        r"\bimport\s+ctypes\b",
        r"\b__import__\s*\(",
        r"\bopen\s*\([^)]*['\"][wWa]\+?['\"]",  # Write mode file access
        r"\bfork\s*\(",
        r"\bpty\b",
    ],
    "javascript": [
        r"\bchild_process\b",
        r"\bfs\.(unlink|rm|rmdir|writeFile|appendFile)\b",
        r"\bprocess\.(kill|exit)\b",
        r"\brequire\s*\(\s*['\"](net|dgram|child_process)['\"]\s*\)",
        r"\bimport.*from\s*['\"]child_process['\"]",
    ],
    "c": [
        r"#include\s*<windows\.h>",
        r"#include\s*<sys/socket\.h>",
        r"#include\s*<unistd\.h>",
        r"\bsystem\s*\(",
        r"\bpopen\s*\(",
        r"\bfork\s*\(",
        r"\bexec[lv][pe]?\s*\(",
        r"\bremove\s*\(",
    ],
    "cpp": [
        r"#include\s*<windows\.h>",
        r"#include\s*<sys/socket\.h>",
        r"#include\s*<unistd\.h>",
        r"#include\s*<filesystem>",
        r"\bsystem\s*\(",
        r"\bpopen\s*\(",
        r"\bfork\s*\(",
        r"\bexec[lv][pe]?\s*\(",
        r"\bremove\s*\(",
    ],
    "java": [
        r"\bProcessBuilder\b",
        r"\bRuntime\.getRuntime\(\)",
        r"\bjava\.net\.",
        r"\bjava\.lang\.reflect\.",
        r"\bSystem\.exit\b",
    ],
}


def sanitize_and_validate_code(language: str, code: str) -> Tuple[bool, Optional[str]]:
    """
    Static security screening before passing code to child process.
    Prevents unauthorized system calls, network access, or filesystem abuse.
    """
    lang_key = (language or "").strip().lower()
    patterns = PROHIBITED_PATTERNS.get(lang_key, [])
    for pat in patterns:
        if re.search(pat, code, re.IGNORECASE):
            return False, f"Security Violation: Prohibited token or system call detected in {language} submission."
    return True, None


# ==============================================================================
# SECURE ISOLATED RUNNERS
# ==============================================================================

class SecureExecutionSandbox:
    """
    Executes user-submitted code inside an isolated temporary directory
    with strict wall-clock timeout and memory constraints.
    """

    PYTHON_PATH = sys.executable
    NODE_PATH = shutil.which("node")
    GCC_PATH = shutil.which("gcc")
    GPP_PATH = shutil.which("g++")
    JAVAC_PATH = shutil.which("javac")
    JAVA_PATH = shutil.which("java")

    @classmethod
    def get_clean_env(cls) -> Dict[str, str]:
        """Provides minimal environment variables without exposing Django or server credentials."""
        safe_keys = ["SYSTEMROOT", "WINDIR", "PATH", "TMP", "TEMP"]
        env = {k: os.environ[k] for k in safe_keys if k in os.environ}
        # Python specific isolation
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        return env

    @classmethod
    def run_process(
        cls,
        cmd: List[str],
        cwd: str,
        input_data: str = "",
        timeout_seconds: float = 3.0,
    ) -> Dict[str, Any]:
        """Runs executable with input, strict timeout, and output capture."""
        start_time = time.perf_counter()
        try:
            proc = subprocess.run(
                cmd,
                input=input_data,
                text=True,
                capture_output=True,
                cwd=cwd,
                timeout=timeout_seconds,
                env=cls.get_clean_env(),
            )
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return {
                "success": proc.returncode == 0,
                "stdout": proc.stdout or "",
                "stderr": proc.stderr or "",
                "exit_code": proc.returncode,
                "timed_out": False,
                "runtime_ms": round(elapsed_ms, 2),
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Time Limit Exceeded: Process exceeded {timeout_seconds}s limit.",
                "exit_code": -1,
                "timed_out": True,
                "runtime_ms": round(timeout_seconds * 1000.0, 2),
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Runtime Execution Failure: {str(e)}",
                "exit_code": -1,
                "timed_out": False,
                "runtime_ms": 0.0,
            }

    @classmethod
    def execute_code(
        cls,
        language: str,
        code: str,
        input_data: str = "",
        time_limit: float = 3.0,
    ) -> Dict[str, Any]:
        """
        Executes code for any supported language in an isolated sandbox.
        Returns:
            {
                "status": "ACCEPTED" | "WRONG_ANSWER" | "TIME_LIMIT_EXCEEDED" | "COMPILATION_ERROR" | "RUNTIME_ERROR",
                "output": str,
                "error": str,
                "runtime_ms": float,
            }
        """
        lang = (language or "").strip().lower()
        is_safe, sec_err = sanitize_and_validate_code(lang, code)
        if not is_safe:
            return {
                "status": "RUNTIME_ERROR",
                "output": "",
                "error": sec_err,
                "runtime_ms": 0.0,
            }

        with tempfile.TemporaryDirectory(prefix="hn_sandbox_") as tmp_dir:
            if lang == "python":
                file_path = os.path.join(tmp_dir, "solution.py")
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(code)
                cmd = [cls.PYTHON_PATH, "-I", file_path]
                res = cls.run_process(cmd, cwd=tmp_dir, input_data=input_data, timeout_seconds=time_limit)

            elif lang in ("javascript", "js"):
                if not cls.NODE_PATH:
                    return {
                        "status": "RUNTIME_ERROR",
                        "output": "",
                        "error": "Node.js runtime engine is not installed or available on this server.",
                        "runtime_ms": 0.0,
                    }
                file_path = os.path.join(tmp_dir, "solution.js")
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(code)
                cmd = [cls.NODE_PATH, file_path]
                res = cls.run_process(cmd, cwd=tmp_dir, input_data=input_data, timeout_seconds=time_limit)

            elif lang == "c":
                if not cls.GCC_PATH:
                    return {
                        "status": "RUNTIME_ERROR",
                        "output": "",
                        "error": "GCC compiler is not available on this server.",
                        "runtime_ms": 0.0,
                    }
                src_path = os.path.join(tmp_dir, "solution.c")
                exe_path = os.path.join(tmp_dir, "solution.exe")
                with open(src_path, "w", encoding="utf-8") as f:
                    f.write(code)
                # Compile step
                compile_cmd = [cls.GCC_PATH, src_path, "-O2", "-o", exe_path]
                c_res = cls.run_process(compile_cmd, cwd=tmp_dir, timeout_seconds=6.0)
                if not c_res["success"]:
                    return {
                        "status": "COMPILATION_ERROR",
                        "output": "",
                        "error": f"Compilation Error:\n{c_res['stderr']}",
                        "runtime_ms": c_res["runtime_ms"],
                    }
                res = cls.run_process([exe_path], cwd=tmp_dir, input_data=input_data, timeout_seconds=time_limit)

            elif lang in ("cpp", "c++"):
                if not cls.GPP_PATH:
                    return {
                        "status": "RUNTIME_ERROR",
                        "output": "",
                        "error": "G++ compiler is not available on this server.",
                        "runtime_ms": 0.0,
                    }
                src_path = os.path.join(tmp_dir, "solution.cpp")
                exe_path = os.path.join(tmp_dir, "solution.exe")
                with open(src_path, "w", encoding="utf-8") as f:
                    f.write(code)
                # Compile step
                compile_cmd = [cls.GPP_PATH, src_path, "-O2", "-std=c++17", "-o", exe_path]
                c_res = cls.run_process(compile_cmd, cwd=tmp_dir, timeout_seconds=6.0)
                if not c_res["success"]:
                    return {
                        "status": "COMPILATION_ERROR",
                        "output": "",
                        "error": f"Compilation Error:\n{c_res['stderr']}",
                        "runtime_ms": c_res["runtime_ms"],
                    }
                res = cls.run_process([exe_path], cwd=tmp_dir, input_data=input_data, timeout_seconds=time_limit)

            elif lang == "java":
                if not cls.JAVAC_PATH or not cls.JAVA_PATH:
                    return {
                        "status": "RUNTIME_ERROR",
                        "output": "",
                        "error": "Java JDK (javac/java) is not available on this server.",
                        "runtime_ms": 0.0,
                    }
                # Find public class or default to Solution
                class_match = re.search(r"public\s+class\s+([A-Za-z0-9_]+)", code)
                class_name = class_match.group(1) if class_match else "Solution"
                src_path = os.path.join(tmp_dir, f"{class_name}.java")
                with open(src_path, "w", encoding="utf-8") as f:
                    f.write(code)
                # Compile step
                compile_cmd = [cls.JAVAC_PATH, src_path]
                c_res = cls.run_process(compile_cmd, cwd=tmp_dir, timeout_seconds=8.0)
                if not c_res["success"]:
                    return {
                        "status": "COMPILATION_ERROR",
                        "output": "",
                        "error": f"Java Compilation Error:\n{c_res['stderr']}",
                        "runtime_ms": c_res["runtime_ms"],
                    }
                res = cls.run_process([cls.JAVA_PATH, "-cp", tmp_dir, class_name], cwd=tmp_dir, input_data=input_data, timeout_seconds=time_limit)

            else:
                return {
                    "status": "RUNTIME_ERROR",
                    "output": "",
                    "error": f"Unsupported programming language '{language}'.",
                    "runtime_ms": 0.0,
                }

            # Map result to status
            if res.get("timed_out"):
                status = "TIME_LIMIT_EXCEEDED"
            elif not res["success"]:
                status = "RUNTIME_ERROR"
            else:
                status = "ACCEPTED"

            return {
                "status": status,
                "output": res["stdout"].strip(),
                "error": res["stderr"].strip(),
                "runtime_ms": res["runtime_ms"],
            }


def normalize_output(text: str) -> str:
    """Normalizes output strings by trimming line ends and standardized newlines."""
    if text is None:
        return ""
    lines = [line.rstrip() for line in str(text).strip().splitlines()]
    return "\n".join(lines)


def evaluate_submission_against_problem(
    problem,
    code: str,
    language: str,
    custom_input: Optional[str] = None,
    is_submit: bool = False,
) -> Dict[str, Any]:
    """
    Evaluates student code against test cases (all test cases on Submit,
    or public sample test cases / custom input on Run Code).
    """
    time_limit = float(problem.time_limit_seconds or 3.0)

    # Mode 1: Custom input single execution
    if custom_input is not None and not is_submit:
        run_res = SecureExecutionSandbox.execute_code(language, code, input_data=custom_input, time_limit=time_limit)
        return {
            "mode": "custom_run",
            "status": run_res["status"],
            "stdout": run_res["output"],
            "stderr": run_res["error"],
            "runtime_ms": run_res["runtime_ms"],
            "test_results": [],
            "passed_count": 1 if run_res["status"] == "ACCEPTED" else 0,
            "total_count": 1,
        }

    # Mode 2: Test cases execution
    test_cases_qs = problem.test_cases.all()
    if not is_submit:
        # On 'Run Code', only execute public (is_hidden=False) sample test cases
        test_cases_qs = test_cases_qs.filter(is_hidden=False)

    test_cases = list(test_cases_qs)
    if not test_cases:
        # If no explicit test cases defined, run with empty input
        res = SecureExecutionSandbox.execute_code(language, code, input_data="", time_limit=time_limit)
        return {
            "mode": "submit" if is_submit else "run",
            "status": res["status"],
            "stdout": res["output"],
            "stderr": res["error"],
            "runtime_ms": res["runtime_ms"],
            "test_results": [],
            "passed_count": 1 if res["status"] == "ACCEPTED" else 0,
            "total_count": 1,
        }

    results = []
    overall_status = "ACCEPTED"
    passed_count = 0
    max_runtime = 0.0

    for idx, tc in enumerate(test_cases, start=1):
        exec_res = SecureExecutionSandbox.execute_code(language, code, input_data=tc.input_data, time_limit=time_limit)
        max_runtime = max(max_runtime, exec_res["runtime_ms"])

        if exec_res["status"] == "COMPILATION_ERROR":
            return {
                "mode": "submit" if is_submit else "run",
                "status": "COMPILATION_ERROR",
                "stdout": "",
                "stderr": exec_res["error"],
                "runtime_ms": exec_res["runtime_ms"],
                "test_results": [],
                "passed_count": 0,
                "total_count": len(test_cases),
            }

        norm_actual = normalize_output(exec_res["output"])
        norm_expected = normalize_output(tc.expected_output)

        is_passed = (exec_res["status"] == "ACCEPTED") and (norm_actual == norm_expected)
        if is_passed:
            passed_count += 1
            tc_status = "PASSED"
        else:
            if exec_res["status"] in ("TIME_LIMIT_EXCEEDED", "RUNTIME_ERROR"):
                tc_status = exec_res["status"]
            else:
                tc_status = "WRONG_ANSWER"
            if overall_status == "ACCEPTED":
                overall_status = tc_status

        tc_report = {
            "case_number": idx,
            "is_hidden": tc.is_hidden,
            "status": tc_status,
            "runtime_ms": exec_res["runtime_ms"],
            "input": "Hidden Test Case" if (tc.is_hidden and is_submit) else tc.input_data,
            "expected_output": "Hidden Test Case" if (tc.is_hidden and is_submit) else tc.expected_output,
            "actual_output": "Hidden Output" if (tc.is_hidden and is_submit and not is_passed) else norm_actual,
            "error": exec_res["error"],
        }
        results.append(tc_report)

    if passed_count == len(test_cases):
        overall_status = "ACCEPTED"

    return {
        "mode": "submit" if is_submit else "run",
        "status": overall_status,
        "stdout": "",
        "stderr": "",
        "runtime_ms": round(max_runtime, 2),
        "test_results": results,
        "passed_count": passed_count,
        "total_count": len(test_cases),
    }
