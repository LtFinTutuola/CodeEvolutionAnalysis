"""
Python wrapper for the persistent Roslyn C# server.

Ported from DroidAgent v1's roslyn_server.py.
Extended with the CENSUS_EXTRACT command for fully-qualified semantic identity mapping.
"""

import os
import json
import subprocess
import threading
from typing import List, Dict
from src.utils import SENTINEL, logger


class RoslynServerWrapper:
    def __init__(self, tool_dir: str, target_framework: str = "net10.0"):
        self.tool_dir = tool_dir
        self.target_framework = target_framework
        self.process = None
        self.lock = threading.Lock()

    def _get_exe_path(self) -> str:
        """Resolve the built executable path based on target framework."""
        return os.path.join(
            self.tool_dir, "bin", "Release", self.target_framework, "SemanticMapper.exe"
        )

    def ensure_built(self):
        """Build the Roslyn server if not already compiled."""
        exe_path = self._get_exe_path()
        if os.path.exists(exe_path):
            return

        logger.info(f"Building Roslyn Server (target: {self.target_framework})...")

        # Dynamically patch the .csproj with the correct target framework
        csproj_path = os.path.join(self.tool_dir, "SemanticMapper.csproj")
        if os.path.exists(csproj_path):
            with open(csproj_path, "r", encoding="utf-8") as f:
                content = f.read()
            # Replace the TargetFramework value if it differs
            import re
            content = re.sub(
                r"<TargetFramework>[^<]+</TargetFramework>",
                f"<TargetFramework>{self.target_framework}</TargetFramework>",
                content,
            )
            with open(csproj_path, "w", encoding="utf-8") as f:
                f.write(content)

        result = subprocess.run(
            "dotnet build -c Release",
            cwd=self.tool_dir,
            shell=True,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.error(f"Roslyn Server build failed:\n{result.stderr}")
            raise RuntimeError(f"dotnet build failed: {result.stderr}")
        logger.info("Roslyn Server built successfully.")

    def start(self):
        """Start the persistent Roslyn server process."""
        self.ensure_built()
        exe_path = self._get_exe_path()

        logger.info("Starting Persistent Roslyn Server...")
        if os.path.exists(exe_path):
            cmd = exe_path
        else:
            cmd = ["dotnet", "run", "-c", "Release"]

        self.process = subprocess.Popen(
            cmd,
            cwd=self.tool_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )

        # Wait for the READY handshake
        while True:
            line = self.process.stdout.readline()
            if not line:
                err = self.process.stderr.read()
                logger.error(f"Roslyn Server failed to start. Stderr: {err}")
                raise RuntimeError(f"Roslyn Server failed to start: {err}")
            if "READY" in line:
                logger.info("Roslyn Server is READY.")
                break

    def _send_command(self, command: str, code: str) -> str:
        """
        Send a command + code payload to the server and read the response.
        Auto-restarts the server on pipe failure (once).
        """
        with self.lock:
            for attempt in range(2):
                if not self.process or self.process.poll() is not None:
                    self.start()

                try:
                    self.process.stdin.write(command + "\n")
                    self.process.stdin.write(code + "\n" + SENTINEL + "\n")
                    self.process.stdin.flush()

                    output = []
                    while True:
                        line = self.process.stdout.readline()
                        if not line:
                            if attempt == 0:
                                break  # Try restart
                            return ""
                        line = line.strip("\r\n")
                        if line == SENTINEL:
                            break
                        output.append(line)

                    if line.strip("\r\n") == SENTINEL:
                        return "\n".join(output)

                    self.stop()
                except (BrokenPipeError, ConnectionResetError) as e:
                    logger.error(f"Roslyn Server connection lost: {e}. Attempting restart...")
                    self.stop()
                except Exception as e:
                    logger.error(f"Roslyn Server Error: {e}")
                    return ""
            return ""

    def census_extract(
        self,
        old_code: str,
        new_code: str,
        old_lns: List[int],
        new_lns: List[int],
    ) -> List[Dict]:
        """
        Send a CENSUS_EXTRACT command to the Roslyn server.

        Returns a list of dicts, each containing:
        - signature: Fully qualified method/property signature
        - parent_signature: Fully qualified class signature
        - sanitized_old_code: Comment-stripped, whitespace-normalized old code
        - sanitized_new_code: Comment-stripped, whitespace-normalized new code
        """
        old_lns_str = ",".join(map(str, old_lns))
        new_lns_str = ",".join(map(str, new_lns))
        header = f"CENSUS_EXTRACT|||{old_lns_str}|||{new_lns_str}"
        combined_code = f"{old_code}\n---DELIMITER---\n{new_code}".replace("\r", "")

        res = self._send_command(header, combined_code)
        try:
            return json.loads(res) if res else []
        except Exception as e:
            logger.error(f"Failed to parse Roslyn JSON: {e}. Response: {res[:200]}...")
            return []

    def baseline_extract(self, code: str) -> List[Dict]:
        """
        Send a BASELINE_EXTRACT command to the Roslyn server.
        Returns a list of dicts, each containing:
        - signature: Fully qualified method/property signature
        - parent_signature: Fully qualified class signature
        """
        header = "BASELINE_EXTRACT|||"
        res = self._send_command(header, code)
        try:
            return json.loads(res) if res else []
        except Exception as e:
            logger.error(f"Failed to parse Roslyn JSON: {e}. Response: {res[:200]}...")
            return []

    def stop(self):
        """Terminate the Roslyn server process."""
        if self.process:
            logger.info("Stopping Roslyn Server...")
            try:
                self.process.stdin.write("EXIT\n")
                self.process.stdin.flush()
            except Exception:
                pass
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except Exception:
                self.process.kill()
            self.process = None
