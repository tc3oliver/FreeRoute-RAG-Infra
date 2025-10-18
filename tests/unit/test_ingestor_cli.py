"""
Unit tests for Ingestor CLI.

Tests command-line argument parsing, path validation, and API interaction.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

# Import the CLI module to test
try:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "services" / "ingestor"))
    from cli import main  # type: ignore
except ImportError:
    # Fallback for testing
    def main():  # type: ignore
        pass


class TestIngestorCLI:
    """Test suite for Ingestor CLI."""

    @pytest.fixture
    def mock_requests_post(self):
        """Mock requests.post for testing."""
        with patch("cli.requests.post") as mock_post:
            yield mock_post

    @pytest.fixture
    def mock_path_exists(self):
        """Mock Path.exists for testing."""
        with patch("cli.Path.exists") as mock_exists:
            mock_exists.return_value = True
            yield mock_exists

    @pytest.fixture
    def successful_response(self):
        """Create a successful API response."""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "message": "Ingestion completed successfully",
            "stats": {
                "files_scanned": 10,
                "files_processed": 8,
                "chunks_indexed": 150,
                "graphs_extracted": 5,
                "errors": 2,
            },
            "processed_files": [
                "/data/doc1.md",
                "/data/doc2.txt",
            ],
            "errors": [
                {
                    "file": "/data/error.md",
                    "stage": "chunking",
                    "error": "Failed to read file",
                }
            ],
        }
        return response

    # =========================================================================
    # Test: 基本命令行參數解析
    # =========================================================================

    def test_cli_basic_success(self, mock_requests_post, mock_path_exists, successful_response, capsys):
        """Test successful basic CLI execution."""
        mock_requests_post.return_value = successful_response

        # Simulate command-line arguments
        test_args = ["cli.py", "/data"]
        with patch.object(sys, "argv", test_args):
            try:
                main()
            except SystemExit as e:
                assert e.code is None or e.code == 0

        # Verify API was called
        assert mock_requests_post.called
        call_args = mock_requests_post.call_args

        # Verify URL
        assert call_args[0][0] == "http://localhost:9900/ingest/directory"

        # Verify request payload
        payload = call_args[1]["json"]
        assert payload["path"] == "/data"
        assert payload["collection"] == "chunks"
        assert payload["chunk_size"] == 1000
        assert payload["chunk_overlap"] == 200
        assert payload["extract_graph"] is True
        assert payload["force_reprocess"] is False

    def test_cli_custom_ingestor_url(self, mock_requests_post, mock_path_exists, successful_response):
        """Test CLI with custom ingestor URL."""
        mock_requests_post.return_value = successful_response

        test_args = [
            "cli.py",
            "/data",
            "--ingestor-url",
            "http://custom-server:8080",
        ]
        with patch.object(sys, "argv", test_args):
            try:
                main()
            except SystemExit:
                pass

        # Verify custom URL was used
        call_args = mock_requests_post.call_args
        assert call_args[0][0] == "http://custom-server:8080/ingest/directory"

    def test_cli_custom_collection(self, mock_requests_post, mock_path_exists, successful_response):
        """Test CLI with custom collection name."""
        mock_requests_post.return_value = successful_response

        test_args = [
            "cli.py",
            "/data",
            "--collection",
            "my_collection",
        ]
        with patch.object(sys, "argv", test_args):
            try:
                main()
            except SystemExit:
                pass

        # Verify custom collection was used
        payload = mock_requests_post.call_args[1]["json"]
        assert payload["collection"] == "my_collection"

    def test_cli_custom_chunk_params(self, mock_requests_post, mock_path_exists, successful_response):
        """Test CLI with custom chunk size and overlap."""
        mock_requests_post.return_value = successful_response

        test_args = [
            "cli.py",
            "/data",
            "--chunk-size",
            "500",
            "--chunk-overlap",
            "100",
        ]
        with patch.object(sys, "argv", test_args):
            try:
                main()
            except SystemExit:
                pass

        # Verify custom chunk parameters
        payload = mock_requests_post.call_args[1]["json"]
        assert payload["chunk_size"] == 500
        assert payload["chunk_overlap"] == 100

    def test_cli_no_graph_extraction(self, mock_requests_post, mock_path_exists, successful_response):
        """Test CLI with graph extraction disabled."""
        mock_requests_post.return_value = successful_response

        test_args = [
            "cli.py",
            "/data",
            "--no-graph",
        ]
        with patch.object(sys, "argv", test_args):
            try:
                main()
            except SystemExit:
                pass

        # Verify graph extraction was disabled
        payload = mock_requests_post.call_args[1]["json"]
        assert payload["extract_graph"] is False

    def test_cli_force_reprocess(self, mock_requests_post, mock_path_exists, successful_response):
        """Test CLI with force reprocess flag."""
        mock_requests_post.return_value = successful_response

        test_args = [
            "cli.py",
            "/data",
            "--force",
        ]
        with patch.object(sys, "argv", test_args):
            try:
                main()
            except SystemExit:
                pass

        # Verify force reprocess was enabled
        payload = mock_requests_post.call_args[1]["json"]
        assert payload["force_reprocess"] is True

    def test_cli_custom_file_patterns(self, mock_requests_post, mock_path_exists, successful_response):
        """Test CLI with custom file patterns."""
        mock_requests_post.return_value = successful_response

        test_args = [
            "cli.py",
            "/data",
            "--file-patterns",
            "*.pdf",
            "*.docx",
        ]
        with patch.object(sys, "argv", test_args):
            try:
                main()
            except SystemExit:
                pass

        # Verify custom file patterns
        payload = mock_requests_post.call_args[1]["json"]
        assert payload["file_patterns"] == ["*.pdf", "*.docx"]

    # =========================================================================
    # Test: 錯誤處理
    # =========================================================================

    def test_cli_path_not_exists(self, capsys):
        """Test CLI with non-existent path."""
        with patch("cli.Path.exists", return_value=False):
            test_args = ["cli.py", "/nonexistent"]
            with patch.object(sys, "argv", test_args):
                with pytest.raises(SystemExit) as exc_info:
                    main()

                # Verify exit code is 1
                assert exc_info.value.code == 1

            # Verify error message
            captured = capsys.readouterr()
            assert "錯誤：路徑不存在" in captured.out

    def test_cli_api_request_error(self, mock_path_exists, capsys):
        """Test CLI with API request error."""
        with patch("cli.requests.post") as mock_post:
            mock_post.side_effect = requests.RequestException("Connection refused")

            test_args = ["cli.py", "/data"]
            with patch.object(sys, "argv", test_args):
                with pytest.raises(SystemExit) as exc_info:
                    main()

                # Verify exit code is 1
                assert exc_info.value.code == 1

            # Verify error message
            captured = capsys.readouterr()
            assert "API 呼叫失敗" in captured.out
            assert "Connection refused" in captured.out

    def test_cli_api_http_error(self, mock_path_exists, capsys):
        """Test CLI with HTTP error response."""
        with patch("cli.requests.post") as mock_post:
            response = MagicMock()
            response.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
            mock_post.return_value = response

            test_args = ["cli.py", "/data"]
            with patch.object(sys, "argv", test_args):
                with pytest.raises(SystemExit) as exc_info:
                    main()

                # Verify exit code is 1
                assert exc_info.value.code == 1

            # Verify error message
            captured = capsys.readouterr()
            assert "API 呼叫失敗" in captured.out

    def test_cli_api_invalid_json(self, mock_path_exists, capsys):
        """Test CLI with invalid JSON response."""
        with patch("cli.requests.post") as mock_post:
            response = MagicMock()
            response.json.side_effect = ValueError("Invalid JSON")
            mock_post.return_value = response

            test_args = ["cli.py", "/data"]
            with patch.object(sys, "argv", test_args):
                with pytest.raises(SystemExit) as exc_info:
                    main()

                # Verify exit code is 1
                assert exc_info.value.code == 1

            # Verify error message
            captured = capsys.readouterr()
            assert "未知錯誤" in captured.out

    # =========================================================================
    # Test: 輸出顯示
    # =========================================================================

    def test_cli_output_format(self, mock_requests_post, mock_path_exists, successful_response, capsys):
        """Test CLI output format."""
        mock_requests_post.return_value = successful_response

        test_args = ["cli.py", "/data"]
        with patch.object(sys, "argv", test_args):
            try:
                main()
            except SystemExit:
                pass

        captured = capsys.readouterr()

        # Verify output contains key information
        assert "開始匯入目錄" in captured.out
        assert "/data" in captured.out
        assert "匯入完成" in captured.out
        assert "統計資訊" in captured.out
        assert "files_scanned: 10" in captured.out
        assert "已處理文件" in captured.out
        assert "/data/doc1.md" in captured.out

    def test_cli_output_with_errors(self, mock_requests_post, mock_path_exists, capsys):
        """Test CLI output when there are errors."""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "message": "Completed with errors",
            "stats": {
                "files_scanned": 5,
                "files_processed": 3,
                "chunks_indexed": 50,
                "graphs_extracted": 2,
                "errors": 2,
            },
            "processed_files": [],
            "errors": [
                {
                    "file": "/data/error1.md",
                    "stage": "embedding",
                    "error": "API timeout",
                },
                {
                    "file": "/data/error2.txt",
                    "stage": "graph_extraction",
                    "error": "Invalid JSON",
                },
            ],
        }
        mock_requests_post.return_value = response

        test_args = ["cli.py", "/data"]
        with patch.object(sys, "argv", test_args):
            try:
                main()
            except SystemExit:
                pass

        captured = capsys.readouterr()

        # Verify error section is displayed
        assert "錯誤" in captured.out
        assert "/data/error1.md" in captured.out
        assert "API timeout" in captured.out
        assert "/data/error2.txt" in captured.out
        assert "Invalid JSON" in captured.out

    def test_cli_output_many_files_truncated(self, mock_requests_post, mock_path_exists, capsys):
        """Test CLI output truncates when there are many files."""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "message": "Completed",
            "stats": {
                "files_scanned": 20,
                "files_processed": 20,
                "chunks_indexed": 500,
                "graphs_extracted": 15,
                "errors": 0,
            },
            "processed_files": [f"/data/doc{i}.md" for i in range(1, 21)],
            "errors": [],
        }
        mock_requests_post.return_value = response

        test_args = ["cli.py", "/data"]
        with patch.object(sys, "argv", test_args):
            try:
                main()
            except SystemExit:
                pass

        captured = capsys.readouterr()

        # Verify only first 10 files are shown
        assert "/data/doc1.md" in captured.out
        assert "/data/doc10.md" in captured.out
        # Should show "... and 10 more files"
        assert "其他 10 個檔案" in captured.out

    # =========================================================================
    # Test: 組合參數
    # =========================================================================

    def test_cli_all_options_combined(self, mock_requests_post, mock_path_exists, successful_response):
        """Test CLI with all options combined."""
        mock_requests_post.return_value = successful_response

        test_args = [
            "cli.py",
            "/data",
            "--ingestor-url",
            "http://custom:8080",
            "--collection",
            "test_collection",
            "--file-patterns",
            "*.md",
            "*.rst",
            "--chunk-size",
            "800",
            "--chunk-overlap",
            "150",
            "--no-graph",
            "--force",
        ]
        with patch.object(sys, "argv", test_args):
            try:
                main()
            except SystemExit:
                pass

        # Verify all options were applied
        call_args = mock_requests_post.call_args
        assert call_args[0][0] == "http://custom:8080/ingest/directory"

        payload = call_args[1]["json"]
        assert payload["path"] == "/data"
        assert payload["collection"] == "test_collection"
        assert payload["file_patterns"] == ["*.md", "*.rst"]
        assert payload["chunk_size"] == 800
        assert payload["chunk_overlap"] == 150
        assert payload["extract_graph"] is False
        assert payload["force_reprocess"] is True
