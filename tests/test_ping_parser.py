import pytest

from s_mapper import parse_ping_output


@pytest.mark.parametrize("output,expected_pct,expected_color", [
    ("Packets: Sent = 4, Received = 4, Lost = 0 (0% loss)", 0, 'green'),
    ("Packets: Sent = 4, Received = 0, Lost = 4 (100% loss)", 100, 'red'),
    ("4 packets transmitted, 0 received, 100% packet loss, time 3003ms", 100, 'red'),
    ("4 packets transmitted, 4 received, 0% packet loss", 0, 'green'),
    ("", None, 'green'),
    (None, None, 'green'),
])
def test_parse_ping_output(output, expected_pct, expected_color):
    pct, color = parse_ping_output(output)
    assert pct == expected_pct
    assert color == expected_color
