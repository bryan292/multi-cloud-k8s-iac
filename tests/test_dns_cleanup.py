import importlib.util
import unittest
spec = importlib.util.spec_from_file_location('dns_records', 'scripts/dns_records.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
class DNSCleanupTests(unittest.TestCase):
    host = 'iac-smoke-unique.test.example.com'
    def fetch(self, *args):
        # Route53 can return adjacent records; they must never be deleted.
        return {'ResourceRecordSets':[
            {'Name':self.host+'.','Type':'A'},
            {'Name':'a-'+self.host+'.','Type':'TXT'},
            {'Name':'aaaa-'+self.host+'.','Type':'TXT'},
            {'Name':'another.test.example.com.','Type':'A'},
            {'Name':self.host+'.unrelated.example.com.','Type':'TXT'},
        ]}
    def test_cleanup_includes_prefixed_ownership_only(self):
        result = m.records_for_test(self.fetch, 'ZTEST', self.host, True)
        self.assertEqual({r['Name'] for r in result}, {self.host+'.','a-'+self.host+'.','aaaa-'+self.host+'.'})
        self.assertEqual(len(result), 3)
    def test_dns_check_only_returns_endpoint_records(self):
        self.assertEqual(m.records_for_test(self.fetch, 'ZTEST', self.host), [{'Name':self.host+'.','Type':'A'}])
