"""Whitelist-only bridge from upstream parsed LTE RRC traces to MAC context."""
import re


def message_types(text):
    return [name for name in re.findall(r'\bc1:\s*([A-Za-z][A-Za-z0-9-]*)\s*\(', text)
            if not re.search(r'-r\d+$', name)]


def mac_context(text):
    result = {}
    patterns = {'periodicBSR-Timer':r'sf\d+|infinity',
                'retxBSR-Timer':r'sf\d+', 'timeAlignmentTimerDedicated':r'sf\d+|infinity'}
    for field, pattern in patterns.items():
        match = re.search(r'(?m)^\s*'+re.escape(field)+r':\s*('+pattern+r')\b', text)
        if match:
            result[field] = match.group(1)
    return result


def integrate_fragment(current_mac, fragment):
    """Return a planning artifact. No encoding, protocol transmission or deployment."""
    allowed = {'periodicBSR-Timer','retxBSR-Timer','timeAlignmentTimerDedicated'}
    if set(current_mac)-allowed:
        raise ValueError('Non-whitelisted source field')
    return {'protocol':'LTE', 'message':'rrcConnectionReconfiguration',
            'radioResourceConfigDedicated':{'mac-MainConfig':{**current_mac, **fragment}},
            'status':'configuration planning fragment; not ASN.1 encoded or transmitted'}
