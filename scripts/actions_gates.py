"""Secret-free workflow gate diagnostics; no network, storage or provider imports."""
import json
import os
import re

ADMIN_MODES = {'bootstrap', 'discover', 'repair-discover', 'authorize', 'renewal-plan', 'renew', 'expand', 'status', 'replay'}


def evaluate(env):
    admin = env.get('ADMIN_FLAG', '')
    live = env.get('LIVE_FLAG', '')
    reviewed = env.get('REVIEWED_SHA', '')
    event, mode = env.get('EVENT', ''), env.get('MODE', '')
    checks = {
        'main_branch': env.get('REF') == 'refs/heads/main',
        'reviewed_sha_is_full': re.fullmatch(r'[0-9a-fA-F]{40}', reviewed) is not None,
        'reviewed_sha_matches': env.get('SHA') == reviewed and bool(reviewed),
        'admin_enabled': admin.strip() == 'true',
        'live_enabled': live.strip() == 'true',
        'admin_flag_has_whitespace': admin != admin.strip(),
        'live_flag_has_whitespace': live != live.strip(),
        'manual_admin_mode': event == 'workflow_dispatch' and mode in ADMIN_MODES,
        'live_mode': event == 'schedule' or event == 'workflow_dispatch' and mode == 'live',
    }
    checks['mode_authorized'] = (checks['manual_admin_mode'] and checks['admin_enabled'] or
                                 checks['live_mode'] and checks['live_enabled'])
    checks['private_authorized'] = all(checks[k] for k in
        ('main_branch', 'reviewed_sha_is_full', 'reviewed_sha_matches', 'mode_authorized'))
    return checks


def main():
    checks = evaluate(os.environ)
    # Boolean allowlist only. Never dump contexts, arbitrary inputs or secrets.
    print(json.dumps(checks, sort_keys=True, indent=2))
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
            stream.write('private_authorized=' + str(checks['private_authorized']).lower() + '\n')


if __name__ == '__main__': main()
