import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import install_scheduled_agents as installer
from evidence_documents import digest


class LoginPersistenceTests(unittest.TestCase):
    def test_exact_idempotent_copy_without_secrets_or_bootstrap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'job';source.mkdir();body=b'<plist>test-only</plist>'
            (source/'evidence.plist').write_bytes(body)
            job={'labels':{'evidence':'fixture.evidence'}}
            installation={'tasks':[{'phase':'evidence','label':'fixture.evidence','plist_sha256':digest(body)}]}
            with patch.object(installer.pilot,'BASE',source):
                first=installer.persist(job,installation,root/'agents')
                self.assertEqual(first,installer.persist(job,installation,root/'agents'))
                self.assertEqual((root/'agents/fixture.evidence.plist').read_bytes(),body)
                (root/'agents/fixture.evidence.plist').write_bytes(b'different')
                with self.assertRaises(ValueError):installer.persist(job,installation,root/'agents')

    def test_changed_source_hash_or_label_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'evidence.plist').write_bytes(b'changed')
            job={'labels':{'evidence':'fixture.evidence'}}
            with patch.object(installer.pilot,'BASE',root):
                for sha,label in ((digest(b'original'),'fixture.evidence'),(digest(b'changed'),'wrong.label')):
                    with self.assertRaises(ValueError):installer.persist(job,{'tasks':[{'phase':'evidence','label':label,'plist_sha256':sha}]},root/'agents')


if __name__=='__main__':unittest.main()
