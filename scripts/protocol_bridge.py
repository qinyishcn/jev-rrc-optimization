"""Use the actual upstream parser and HF data; publish only protocol type labels."""
import importlib.util
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pandas as pd
from rrcopt.protocol import message_types, mac_context
from rrcopt.provenance import file_hash


def main():
    spec = importlib.util.spec_from_file_location('upstream_rrc_utils', 'external/nrrrc/rrc_utils.py')
    upstream = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(upstream)
    messages = upstream.parse_rrc_log('external/nrrrc/demo.txt')
    pairs = upstream.create_qa_dataset(messages)
    df = pd.read_parquet('data/rrc/demo.parquet')
    assert len(pairs)==len(df)==16
    current_mac = next(mac_context(text) for text in df.A_Content if mac_context(text))
    safe_rows = [{'row':int(i), 'ul_types':message_types(r.Q_Content),
                  'observed_dl_types':message_types(r.A_Content)} for i,r in df.iterrows()]
    assert all(row['ul_types'] and row['observed_dl_types'] for row in safe_rows)
    payload = {'dataset_sha256':file_hash('data/rrc/demo.parquet'),
               'upstream_parser_sha256':file_hash('external/nrrrc/rrc_utils.py'),
               'parsed_messages':len(messages), 'paired_rows':len(pairs),
               'current_mac':current_mac,
               'scope':'Only observed MAC values are integrated; DRX and QoS labels are absent.'}
    Path('artifacts/protocol_context.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
    Path('artifacts/protocol_labels.json').write_text(json.dumps(safe_rows,indent=2),encoding='utf-8')
    print(json.dumps(payload,indent=2))


if __name__=='__main__':
    main()
