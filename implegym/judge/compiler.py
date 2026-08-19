"""Multi-compiler management, profile configuration, and code compilation."""

import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from implegym.config import settings
from implegym.models.schemas import CompilerProfileSchema


@dataclass
class CompilationResult:
    """Result of a compilation attempt."""

    success: bool
    executable_path: Optional[Path] = None
    source_path: Optional[Path] = None
    diagnostics: str = ""
    error_type: Optional[str] = None  # "CE" or None


class CompilerManager:
    """Manages compiler detection, profiles, and invocation."""

    # Built-in supported compiler profile definitions
    PROFILES: Dict[str, Dict[str, str]] = {
        "g++ (C++20)": {
            "executable": "g++",
            "language": "cpp",
            "standard": "c++20",
            "default_flags": "-O3 -Wall -Wextra",
        },
        "g++ (C++17)": {
            "executable": "g++",
            "language": "cpp",
            "standard": "c++17",
            "default_flags": "-O3 -Wall -Wextra",
        },
        "g++ (C++23)": {
            "executable": "g++",
            "language": "cpp",
            "standard": "c++23",
            "default_flags": "-O3 -Wall -Wextra",
        },
        "clang++ (C++20)": {
            "executable": "clang++",
            "language": "cpp",
            "standard": "c++20",
            "default_flags": "-O3 -Wall -Wextra",
        },
        "clang++ (C++23)": {
            "executable": "clang++",
            "language": "cpp",
            "standard": "c++23",
            "default_flags": "-O3 -Wall -Wextra",
        },
        "python3": {
            "executable": "python",
            "language": "python",
            "standard": "py3",
            "default_flags": "",
        },
    }

    def __init__(self, sandbox_base: Optional[Path] = None) -> None:
        self.sandbox_base = sandbox_base or settings.sandbox_dir
        self.sandbox_base.mkdir(parents=True, exist_ok=True)

    def get_available_profiles(self) -> List[CompilerProfileSchema]:
        """Detect and return compiler profiles available on the current machine."""
        available: List[CompilerProfileSchema] = []
        for name, cfg in self.PROFILES.items():
            exec_name = cfg["executable"]
            is_present = shutil.which(exec_name) is not None
            if is_present or name.startswith("g++") or name == "python3":
                available.append(
                    CompilerProfileSchema(
                        id=name,
                        name=name,
                        executable=exec_name,
                        language=cfg["language"],
                        default_flags=cfg["default_flags"],
                        supported_standards=[cfg["standard"]],
                    )
                )
        return available

    def compile(
        self,
        code: str,
        compiler_profile: str = "g++ (C++20)",
        custom_flags: Optional[str] = None,
    ) -> CompilationResult:
        """Compile source code into executable in isolated sandbox."""
        config = self.PROFILES.get(compiler_profile)
        if not config:
            # Fallback to g++ (C++20)
            config = self.PROFILES["g++ (C++20)"]

        session_id = uuid.uuid4().hex[:12]
        session_sandbox = self.sandbox_base / session_id
        session_sandbox.mkdir(parents=True, exist_ok=True)

        lang = config["language"]
        if lang == "python":
            # Interpreted, write source file directly
            src_file = session_sandbox / "solution.py"
            src_file.write_text(code, encoding="utf-8")
            return CompilationResult(
                success=True,
                executable_path=src_file,
                source_path=src_file,
            )

        # C++ compilation
        src_file = session_sandbox / "solution.cpp"
        src_file.write_text(code, encoding="utf-8")
        
        exe_suffix = ".exe" if os.name == "nt" else ""
        out_file = session_sandbox / f"solution{exe_suffix}"

        compiler_bin = config["executable"]
        std_flag = f"-std={config['standard']}"
        flags = custom_flags if custom_flags is not None else config["default_flags"]

        cmd = [compiler_bin, std_flag] + flags.split() + [str(src_file), "-o", str(out_file)]

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30.0,
                check=False,
            )
            if res.returncode != 0:
                return CompilationResult(
                    success=False,
                    source_path=src_file,
                    diagnostics=res.stderr or res.stdout,
                    error_type="CE",
                )
            return CompilationResult(
                success=True,
                executable_path=out_file,
                source_path=src_file,
                diagnostics=res.stderr,
            )
        except subprocess.TimeoutExpired:
            return CompilationResult(
                success=False,
                source_path=src_file,
                diagnostics="Compilation timed out after 30 seconds",
                error_type="CE",
            )
        except Exception as ex:
            return CompilationResult(
                success=False,
                source_path=src_file,
                diagnostics=f"Failed to invoke compiler: {str(ex)}",
                error_type="CE",
            )
