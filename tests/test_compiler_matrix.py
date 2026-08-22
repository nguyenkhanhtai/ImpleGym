"""Tests for CompilerManager across different standards and diagnostics capture."""

from implegym.judge.compiler import CompilerManager


class TestCompilerManager:
    """Test suite for compilation matrix."""

    def setup_method(self) -> None:
        self.compiler = CompilerManager()

    def test_cpp_compilation_success(self) -> None:
        """Test compiling valid C++20 code."""
        code = """
        #include <iostream>
        int main() {
            std::cout << "OK" << std::endl;
            return 0;
        }
        """
        res = self.compiler.compile(code, compiler_profile="g++ (C++20)")
        assert res.success is True
        assert res.executable_path is not None
        assert res.executable_path.exists()

    def test_cpp_compilation_standards(self) -> None:
        """Test compiling under C++17 standard."""
        code = """
        #include <iostream>
        #include <string_view>
        int main() {
            std::string_view sv = "Hello C++17";
            std::cout << sv << std::endl;
            return 0;
        }
        """
        res = self.compiler.compile(code, compiler_profile="g++ (C++17)")
        assert res.success is True

    def test_cpp_compilation_error_diagnostic(self) -> None:
        """Test capturing compilation error (CE) diagnostics on invalid syntax."""
        code = """
        #include <iostream>
        int main() {
            this is syntax error @@!!
            return 0;
        }
        """
        res = self.compiler.compile(code, compiler_profile="g++ (C++20)")
        assert res.success is False
        assert res.error_type == "CE"
        assert len(res.diagnostics) > 0
        assert "error" in res.diagnostics.lower()

    def test_python_solution_handling(self) -> None:
        """Test Python script handling."""
        code = "print(1 + 2)\n"
        res = self.compiler.compile(code, compiler_profile="python3")
        assert res.success is True
        assert res.source_path is not None
        assert res.source_path.exists()
