"""Verify the pinned phase-one protocol before importing a job verdict."""
import json
import re
from pathlib import Path, PurePosixPath
from jsonschema import Draft202012Validator, FormatChecker
from .settings import PROJECT_KEY, SUITE_ID

SCHEMA_FILE = Path(__file__).parent / 'data/protocol-v1.schema.json'
VALIDATOR = None


class ProtocolError(ValueError):
    pass


def validator():
    global VALIDATOR
    if VALIDATOR is None:
        schema = json.loads(SCHEMA_FILE.read_text())
        Draft202012Validator.check_schema(schema)
        VALIDATOR = Draft202012Validator(schema, format_checker=FormatChecker())
    return VALIDATOR


def validate(value):
    try:
        validator().validate(value)
    except Exception as exc:
        raise ProtocolError('protocol schema validation failed: ' + str(exc).split('\n')[0]) from exc


def artifact_path(root, relative):
    p = PurePosixPath(relative)
    if not relative or p.is_absolute() or '..' in p.parts or str(p) != relative or '\\' in relative:
        raise ProtocolError('invalid artifact path')
    root = Path(root).resolve(strict=True)
    current = root
    for part in p.parts:
        current = current / part
        if current.is_symlink():
            raise ProtocolError('artifact symlinks are not supported')
    if not current.resolve(strict=True).is_relative_to(root):
        raise ProtocolError('artifact escaped run directory')
    return current


def read_json(path, maximum=16 * 1024 * 1024):
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > maximum:
        raise ProtocolError('invalid or oversized JSON artifact')
    return json.loads(path.read_text())


def validate_case(case):
    validate(case)
    if case['failed'] != (case['status'] == 'FAIL'):
        raise ProtocolError('case verdict mismatch')
    seen = set()
    for a in case['assertions']:
        if a['id'] in seen:
            raise ProtocolError('duplicate assertion ID')
        seen.add(a['id'])
        if a['operator'] == 'eq':
            # Python considers True == 1; JSON assertion types must stay distinct.
            passed = json.dumps(a['expected'], sort_keys=True) == json.dumps(a['actual'], sort_keys=True)
        else:
            try:
                if any(isinstance(v, bool) or not (isinstance(v, int) or
                       isinstance(v, str) and re.fullmatch(r'-?[0-9]+', v))
                       for v in [a['actual'], a['expected']]):
                    raise ValueError('not an exact integer')
                passed = int(a['actual']) >= int(a['expected'])
            except (ValueError, TypeError):
                raise ProtocolError('invalid exact-integer comparison')
        if passed != (a['status'] == 'PASS'):
            raise ProtocolError('assertion status contradicts expected/actual')
        if a['status'] == 'FAIL' and not case['failed']:
            raise ProtocolError('failed assertion hidden by case status')


def import_report(job, exit_code, settings, catalog):
    folder = Path(job['output_dir'])
    expected_folder = settings.job_root(job['run_id']) / 'report'
    if folder != expected_folder or folder.is_symlink():
        raise ProtocolError('unexpected report directory')
    report = read_json(artifact_path(folder, 'summary.json'))
    stdout = read_json(settings.job_root(job['run_id']) / 'stdout.json')
    validate(report)
    if report != stdout:
        raise ProtocolError('stdout and saved report disagree')
    expected = {'run_id': job['run_id'], 'run_kind': job['run_kind'], 'suite_id': job['suite_id'],
                'suite_version': job['suite_version'], 'project_id': PROJECT_KEY, 'profile': 'local-synthetic-v1',
                'evidence_dir': str(expected_folder)}
    if any(report.get(k) != v for k, v in expected.items()) or report['exit_code'] != exit_code:
        raise ProtocolError('report identity or process exit code mismatch')
    exits = {'PASS': 0, 'FAIL': 1, 'ENV_ERROR': 2, 'NO_TESTS': 3}
    if exits[report['status']] != report['exit_code'] or exits[report['gate_result']['status']] != report['gate_result']['exit_code']:
        raise ProtocolError('invalid status/exit mapping')
    if report['evidence_errors'] and report['status'] == 'PASS':
        raise ProtocolError('incomplete evidence cannot pass')
    if report.get('diagnostic_filter'):
        raise ProtocolError('managed runs cannot narrow the mandatory scope')
    suite = next(s for s in catalog['suites'] if s['suite_id'] == SUITE_ID)
    required = suite['required_tests'] if job['run_kind'] == 'regression' else [suite['selftest_target']]
    if report['required_tests'] != required:
        raise ProtocolError('mandatory test scope changed')
    if job['run_kind'] == 'regression' and report['status'] != report['gate_result']['status']:
        raise ProtocolError('regression verdict hides original gate verdict')
    cases = {}
    for entry in report['cases']:
        if entry['case_id'] in cases:
            raise ProtocolError('duplicate case evidence')
        case = read_json(artifact_path(folder, entry['evidence_file']))
        validate_case(case)
        if any(case.get(k) != expected[k] for k in ['run_id', 'run_kind', 'suite_id', 'suite_version', 'project_id', 'profile']):
            raise ProtocolError('case belongs to another run')
        if case['case_id'] != entry['case_id']:
            raise ProtocolError('case identity mismatch')
        failed = sum(a['status'] == 'FAIL' for a in case['assertions'])
        if (entry['status'] != case['status'] or entry['assertions_failed'] != failed
                or entry['assertions_passed'] != len(case['assertions']) - failed):
            raise ProtocolError('case summary contradicts assertion evidence')
        cases[case['case_id']] = case
    if report['status'] == 'PASS':
        if not report['source']['sha256'] or report['gate_result']['missing_mandatory']:
            raise ProtocolError('missing source or required tests')
        for name in required:
            if name not in cases or not cases[name]['assertions']:
                raise ProtocolError('required case evidence missing')
        executed = report['gate_result']['passed'] if job['run_kind'] == 'regression' else report['gate_result']['failed']
        if not all(suite['package'] + '/' + name in executed for name in required):
            raise ProtocolError('required tests absent from execution result')
        if job['run_kind'] == 'regression' and (report['gate_result']['failed'] or any(c['failed'] for c in cases.values())):
            raise ProtocolError('regression cannot pass with failing evidence')
        before = read_json(artifact_path(folder, 'metadata.json'))
        after = read_json(artifact_path(folder, 'source-after.json'))
        if report['source']['sha256'] != before['source']['sha256'] or report['source']['sha256'] != after['source']['sha256']:
            raise ProtocolError('source identities disagree')
        if job['run_kind'] == 'selftest':
            target = cases[suite['selftest_target']]
            proof = set()
            wants = {('balance', 'alice/spot/TESTUSD'): ('10000000000', '9999999999'),
                     ('conservation', 'alice/TESTUSD'): ('100000000000', '99999999999'),
                     ('reconciliation', 'alice/spot/TESTUSD'): ('10000000000', '9999999999')}
            for a in target['assertions']:
                key = (a['rule_id'], a['subject'])
                if key in wants and a['status'] == 'FAIL' and a.get('unit') == 'minor:TESTUSD' and (a['expected'], a['actual']) == wants[key]:
                    proof.add(a['rule_id'])
            if proof != {'balance', 'conservation', 'reconciliation'} or report['gate_result']['status'] != 'FAIL' or not report['selftest']['mutation_detected']:
                raise ProtocolError('selftest mutation was not proven')
    for name in report['artifacts']:
        artifact_path(folder, name)
    return report
