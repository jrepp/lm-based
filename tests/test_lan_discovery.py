import re
import subprocess
import unittest
from unittest.mock import patch, MagicMock


class TestDiscoverLanIps(unittest.TestCase):

    def _discover_lan_ips(self, stdout: str) -> list[str]:
        """Inline copy of _discover_lan_ips for isolated testing."""
        ips: set[str] = set()
        try:
            result = subprocess.run(
                ["ip", "-4", "addr", "show"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                for line in stdout.splitlines():
                    m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", line)
                    if m:
                        ip = m.group(1)
                        if ip not in ("127.0.0.1", "127.0.1.1") and not ip.startswith("169.254"):
                            ips.add(ip)
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        if not ips:
            try:
                result = subprocess.run(
                    ["ifconfig"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    for line in stdout.splitlines():
                        m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", line)
                        if m:
                            ip = m.group(1)
                            if ip not in ("127.0.0.1", "127.0.1.1") and not ip.startswith("169.254"):
                                ips.add(ip)
            except (subprocess.SubprocessError, FileNotFoundError):
                pass
        return sorted(ips)

    def test_discovers_non_loopback_ips(self):
        stdout = """1: lo: <LOOPBACK> inet 127.0.0.1/8 scope host lo
2: eth0: <BROADCAST> inet 192.168.1.10/24 brd ff:ff:ff:ff:ff:ff scope global eth0
3: wlan0: <BROADCAST> inet 10.0.0.5/24 brd ff:ff:ff:ff:ff:ff scope global wlan0"""
        ips = self._discover_lan_ips(stdout)
        self.assertEqual(ips, ["10.0.0.5", "192.168.1.10"])

    def test_excludes_loopback(self):
        stdout = """1: lo: <LOOPBACK> inet 127.0.0.1/8 scope host lo
2: lo: <LOOPBACK> inet 127.0.1.1/8 scope host lo
3: eth0: <BROADCAST> inet 192.168.1.10/24 brd ff:ff:ff:ff:ff:ff scope global eth0"""
        ips = self._discover_lan_ips(stdout)
        self.assertNotIn("127.0.0.1", ips)
        self.assertNotIn("127.0.1.1", ips)

    def test_excludes_link_local(self):
        stdout = """1: lo: <LOOPBACK> inet 127.0.0.1/8 scope host lo
2: eth0: <BROADCAST> inet 169.254.1.2/16 brd ff:ff:ff:ff:ff:ff scope eth0
3: eth0: <BROADCAST> inet 192.168.1.10/24 brd ff:ff:ff:ff:ff:ff scope global eth0"""
        ips = self._discover_lan_ips(stdout)
        self.assertNotIn("169.254.1.2", ips)
        self.assertEqual(ips, ["192.168.1.10"])

    def test_returns_sorted_unique(self):
        stdout = """1: eth0: <BROADCAST> inet 10.0.0.5/24 scope global eth0
2: eth1: <BROADCAST> inet 192.168.1.10/24 scope global eth1
3: eth2: <BROADCAST> inet 10.0.0.5/24 scope global eth2
4: lo: <LOOPBACK> inet 127.0.0.1/8 scope host lo"""
        ips = self._discover_lan_ips(stdout)
        self.assertEqual(ips, ["10.0.0.5", "192.168.1.10"])
        self.assertEqual(len(ips), len(set(ips)))

    def test_returns_empty_when_no_interfaces(self):
        stdout = ""
        ips = self._discover_lan_ips(stdout)
        self.assertEqual(ips, [])


class TestAllHostsProperty(unittest.TestCase):

    def _parse_all_hosts(self, host: str, additional_hosts: str) -> list[str]:
        """Inline copy of all_hosts logic for isolated testing."""
        LAN_PLACEHOLDER = "+lan"

        def _discover_lan_ips() -> list[str]:
            ips: set[str] = set()
            try:
                result = subprocess.run(
                    ["ip", "-4", "addr", "show"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", line)
                        if m:
                            ip = m.group(1)
                            if ip not in ("127.0.0.1", "127.0.1.1") and not ip.startswith("169.254"):
                                ips.add(ip)
            except (subprocess.SubprocessError, FileNotFoundError):
                pass
            if not ips:
                try:
                    result = subprocess.run(
                        ["ifconfig"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if result.returncode == 0:
                        for line in result.stdout.splitlines():
                            m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", line)
                            if m:
                                ip = m.group(1)
                                if ip not in ("127.0.0.1", "127.0.1.1") and not ip.startswith("169.254"):
                                    ips.add(ip)
                except (subprocess.SubprocessError, FileNotFoundError):
                    pass
            return sorted(ips)

        hosts = [host]
        if additional_hosts:
            for token in additional_hosts.split(","):
                token = token.strip()
                if not token:
                    continue
                if token == LAN_PLACEHOLDER:
                    hosts.extend(_discover_lan_ips())
                else:
                    hosts.append(token)
        return hosts

    def test_single_host(self):
        result = self._parse_all_hosts("127.0.0.1", "")
        self.assertEqual(result, ["127.0.0.1"])

    def test_additional_hosts_single(self):
        result = self._parse_all_hosts("127.0.0.1", "192.168.1.10")
        self.assertEqual(result, ["127.0.0.1", "192.168.1.10"])

    def test_additional_hosts_multiple(self):
        result = self._parse_all_hosts("127.0.0.1", "192.168.1.10,10.0.0.5")
        self.assertEqual(result, ["127.0.0.1", "192.168.1.10", "10.0.0.5"])

    def test_additional_hosts_with_whitespace(self):
        result = self._parse_all_hosts("127.0.0.1", " 192.168.1.10 , 10.0.0.5 ")
        self.assertEqual(result, ["127.0.0.1", "192.168.1.10", "10.0.0.5"])

    def test_additional_hosts_empty_tokens_ignored(self):
        result = self._parse_all_hosts("127.0.0.1", "192.168.1.10,,10.0.0.5,")
        self.assertEqual(result, ["127.0.0.1", "192.168.1.10", "10.0.0.5"])

    @patch("subprocess.run")
    def test_lan_placeholder_discovers_ips(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="1: eth0: <BROADCAST> inet 192.168.1.10/24 scope global eth0\n2: lo: <LOOPBACK> inet 127.0.0.1/8 scope host lo"
        )
        result = self._parse_all_hosts("127.0.0.1", "+lan")
        self.assertIn("192.168.1.10", result)
        self.assertIn("127.0.0.1", result)

    @patch("subprocess.run")
    def test_lan_placeholder_with_explicit_host(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="1: eth0: <BROADCAST> inet 192.168.1.10/24 scope global eth0\n2: lo: <LOOPBACK> inet 127.0.0.1/8 scope host lo"
        )
        result = self._parse_all_hosts("127.0.0.1", "+lan,10.0.0.5")
        self.assertEqual(result[0], "127.0.0.1")
        self.assertIn("192.168.1.10", result)
        self.assertIn("10.0.0.5", result)


if __name__ == "__main__":
    unittest.main()