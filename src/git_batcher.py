"""
Persistent Git cat-file --batch subprocess for fast blob retrieval.

Ported from DroidAgent v1's git_batcher.py.
Thread-safe: uses a lock to serialize stdin/stdout access.
"""

import threading
import subprocess
from src.utils import logger


class GitBatcher:
    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.process = None
        self.lock = threading.Lock()

    def start(self):
        """Launch the persistent git cat-file --batch process."""
        logger.info("Starting Git Batch Reader (cat-file)...")
        self.process = subprocess.Popen(
            ["git", "cat-file", "--batch"],
            cwd=self.repo_path,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,  # Binary mode for cat-file
            bufsize=0,
        )

    def get_file_content(self, commit_hash: str, filepath: str) -> str:
        """
        Retrieve the content of a file at a specific commit.
        Returns empty string if the file does not exist at that commit.
        """
        with self.lock:
            if not self.process or self.process.poll() is not None:
                self.start()

            try:
                # git cat-file --batch expects "<sha1>:<path>\n"
                query = f"{commit_hash}:{filepath}\n".encode("utf-8")
                self.process.stdin.write(query)
                self.process.stdin.flush()

                # Response format: "<sha> <type> <size>\n<contents>\n"
                header_line = self.process.stdout.readline()
                if not header_line:
                    return ""

                header = header_line.decode("utf-8").strip()
                if "missing" in header or not header:
                    return ""

                parts = header.split()
                if len(parts) < 3:
                    logger.warning(f"Git Batcher malformed header: '{header}'")
                    return ""

                try:
                    size = int(parts[2])

                    bytes_read = 0
                    chunks = []
                    while bytes_read < size:
                        chunk = self.process.stdout.read(size - bytes_read)
                        if not chunk:
                            break
                        chunks.append(chunk)
                        bytes_read += len(chunk)

                    content = b"".join(chunks)

                    # Consume the trailing newline
                    terminator = self.process.stdout.read(1)
                    if terminator != b"\n":
                        logger.warning(
                            f"Git Batcher expected \\n after contents, got {terminator}"
                        )

                    return content.decode("utf-8", errors="replace")
                except ValueError:
                    logger.error(f"Git Batcher size parse error in header: '{header}'")
                    self.stop()
                    return ""
            except Exception as e:
                logger.error(f"Git Batcher Error: {e}")
                self.stop()
                return ""

    def stop(self):
        """Terminate the cat-file process."""
        if self.process:
            logger.info("Stopping Git Batcher...")
            try:
                self.process.stdin.close()
            except Exception:
                pass
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except Exception:
                self.process.kill()
            self.process = None
