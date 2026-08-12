from pathlib import Path
import hashlib, json, re, sys

ROOT = Path(__file__).resolve().parent

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

checks = {}
all_runtime_text = "\n".join(p.read_text(encoding='utf-8') for p in (ROOT/'runtime').glob('*.py')) + "\n" + (ROOT/'schema.sql').read_text(encoding='utf-8')
checks['no_knowledge_record_class'] = 'class KnowledgeRecord' not in all_runtime_text
checks['no_knowledge_records_table'] = not bool(re.search(r'CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?knowledge_records', all_runtime_text, re.I))
checks['memory_status_has_rejected'] = 'REJECTED = "REJECTED"' in (ROOT/'runtime/models.py').read_text(encoding='utf-8')
checks['company_runtime_not_bundled_or_modified'] = not (ROOT/'Company Intelligence Runtime V1.1').exists()
checks['patch_target_count_is_5'] = len([p for p in (ROOT/'prompt_patches').glob('*__V10.2_*_Addendum.md')]) == 5
checks['a5_financial_snapshot_boundary_present'] = 'CURRENT FINANCIAL TRUTH OWNER' in (ROOT/'prompt_patches/Vencertia Financial & Business Model__V10.2_User_Knowledge_Runtime_Addendum.md').read_text(encoding='utf-8')
checks['monetization_distance_1_to_4_patch_present'] = '1, 2, 3, 4' in (ROOT/'prompt_patches/Pydantic JSON Schema__V10.2_User_Knowledge_Runtime_Addendum.md').read_text(encoding='utf-8')

manifest = json.loads((ROOT/'compatibility_audit.json').read_text(encoding='utf-8'))
checks['original_prompt_hashes_present'] = len(manifest.get('original_prompt_sha256', {})) == 15
checks['original_zip_hash_present'] = bool(manifest.get('original_agent_zip_sha256'))

failed = [k for k,v in checks.items() if not v]
print(json.dumps({'checks': checks, 'failed': failed}, indent=2, ensure_ascii=False))
sys.exit(1 if failed else 0)
