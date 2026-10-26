"""Validation of user-supplied SIPp scenario XML.

SIPp can run arbitrary shell commands from a scenario (<exec command="...">)
and read local files, so any account that can submit scenario XML could run
code as the service user. We therefore PARSE the XML and only accept a known
set of scenario elements, instead of searching the text for bad strings.

Operators who really need <exec> can opt in with SIPPTESTER_ALLOW_EXEC=1
(trusted users only).
"""
import os
import re
import xml.etree.ElementTree as ET

MAX_XML_BYTES = 512 * 1024

# Elements of the SIPp scenario language that cannot run programs.
ALLOWED_ELEMENTS = {
    "scenario", "send", "recv", "pause", "nop", "label", "timewait", "action",
    "ereg", "log", "warning", "assign", "assignstr", "add", "subtract", "multiply",
    "divide", "jump", "test", "setdest", "lookup", "strcmp", "verifyauth",
    "gettimeofday", "todouble", "closecon", "sendCmd", "recvCmd", "cmd",
    "Reference", "ResponseTimeRepartition", "CallLengthRepartition", "Global", "User",
}
# Attributes that execute programs or read/play local files, on any element.
DANGEROUS_ATTRIBUTES = {"command", "int_cmd", "play_pcap_audio", "play_pcap_video", "rtp_stream"}
# Message-body keywords that read local files.
_DANGEROUS_KEYWORD = re.compile(r"\[\s*(file|tdmmap)\b", re.IGNORECASE)
_ENTITY = re.compile(r"<!\s*ENTITY", re.IGNORECASE)
_DOCTYPE = re.compile(r"<!\s*DOCTYPE", re.IGNORECASE)
_SIPP_DOCTYPE = re.compile(r'<!DOCTYPE\s+scenario\s+SYSTEM\s+"sipp\.dtd"\s*>')


class ScenarioRejected(ValueError):
    """The scenario contains something not allowed."""


def clean_scenario_xml(raw: str) -> str:
    """Strip the markdown code fences an AI reply may carry. Always validate THIS output."""
    return (raw or "").replace("```xml", "").replace("```", "").strip()


def _exec_allowed() -> bool:
    return os.environ.get("SIPPTESTER_ALLOW_EXEC") == "1"


def validate_scenario_xml(xml: str) -> None:
    """Raise ScenarioRejected if the XML must not be run or stored."""
    xml = clean_scenario_xml(xml)
    if not xml:
        return
    if len(xml.encode("utf-8", "ignore")) > MAX_XML_BYTES:
        raise ScenarioRejected("Scenario is too large (limit 512 KB)")
    if _ENTITY.search(xml):
        raise ScenarioRejected("XML entity declarations are not allowed")
    if _DOCTYPE.search(xml) and not _SIPP_DOCTYPE.search(xml):
        raise ScenarioRejected('Only the standard <!DOCTYPE scenario SYSTEM "sipp.dtd"> declaration is allowed')
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        raise ScenarioRejected(f"Scenario is not valid XML: {e}")
    if root.tag != "scenario":
        raise ScenarioRejected("The root element must be <scenario>")

    allow_exec = _exec_allowed()
    for el in root.iter():
        tag = el.tag if isinstance(el.tag, str) else ""
        if tag == "exec" and not allow_exec:
            raise ScenarioRejected(
                "Scenarios may not use <exec>, which runs shell commands on the server. "
                "Set SIPPTESTER_ALLOW_EXEC=1 to allow it (trusted users only)."
            )
        if tag != "exec" and tag not in ALLOWED_ELEMENTS:
            raise ScenarioRejected(f"Element <{tag}> is not an allowed SIPp scenario element")
        if not allow_exec:
            bad = DANGEROUS_ATTRIBUTES & set(el.attrib)
            if bad:
                raise ScenarioRejected(f"Attribute '{sorted(bad)[0]}' on <{tag}> is not allowed")
        if el.text and _DANGEROUS_KEYWORD.search(el.text):
            raise ScenarioRejected("The [file] keyword is not allowed in scenario messages")


def prepare_scenario_xml(raw: str) -> str:
    """Clean and validate; returns the exact text that may be written to disk and run."""
    validate_scenario_xml(raw)
    return clean_scenario_xml(raw)
