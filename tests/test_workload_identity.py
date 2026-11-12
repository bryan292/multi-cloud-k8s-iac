"""WID-001/004: configuration boundaries and credential-free binding export."""
import copy
import unittest

from scripts.config import load_config, validate


class WorkloadIdentityConfigTests(unittest.TestCase):
    def config(self, provider='aws'):
        c = load_config(f'config.{provider}.yaml_example')
        subscription = c.get('azure', {}).get('subscription_id', '11111111-1111-1111-1111-111111111111')
        c['workload_identities'] = {'reader': {
            'namespace': 'application', 'service_account': 'reader',
            'aws': {'statements': [{'actions': ['s3:GetBucketLocation'], 'resources': ['arn:aws:s3:::application-data']}]},
            'azure': {'role_assignments': [{
                'scope': f'/subscriptions/{subscription}/resourceGroups/application',
                'role_definition_id': f'/subscriptions/{subscription}/providers/Microsoft.Authorization/roleDefinitions/acdd72a7-3385-48ef-bd42-f606fba81ae7',
            }]},
        }}
        return c

    def test_optional_and_both_providers(self):
        for provider in ('aws', 'azure'):
            validate(load_config(f'config.{provider}.yaml_example'))
            validate(self.config(provider))

    def test_invalid_subjects_and_missing_permissions(self):
        for field, value in [('namespace', '*'), ('service_account', 'reader:admin'), ('namespace', 'x' * 64)]:
            c = self.config(); c['workload_identities']['reader'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): validate(c)
        c = self.config(); del c['workload_identities']['reader']['aws']
        with self.assertRaises(ValueError): validate(c)
        c = self.config(); c['workload_identities']['duplicate'] = copy.deepcopy(c['workload_identities']['reader'])
        with self.assertRaisesRegex(ValueError, 'unique'): validate(c)

    def test_aws_scope_and_administration_rejected(self):
        for field, values in [('actions', ['s3:*']), ('actions', ['iam:CreateRole']), ('actions', ['sts:AssumeRole']),
                              ('actions', []), ('resources', ['*']), ('resources', ['arn:aws:s3:::bucket/*']), ('resources', [])]:
            c = self.config(); c['workload_identities']['reader']['aws']['statements'][0][field] = values
            with self.subTest(field=field, values=values), self.assertRaises(ValueError): validate(c)

    def test_azure_scope_and_administration_rejected(self):
        for field, value in [('scope', '/subscriptions/11111111-1111-1111-1111-111111111111'),
                             ('scope', '/subscriptions/ffffffff-ffff-ffff-ffff-ffffffffffff/resourceGroups/other'),
                             ('scope', '/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/*')]:
            c = self.config('azure'); c['workload_identities']['reader']['azure']['role_assignments'][0][field] = value
            with self.subTest(value=value), self.assertRaises(ValueError): validate(c)
        c = self.config('azure'); a = c['workload_identities']['reader']['azure']['role_assignments'][0]
        a['role_definition_id'] = a['role_definition_id'].rsplit('/', 1)[0] + '/8e3af657-a8ff-443c-a75c-2fe8c4bcb635'
        with self.assertRaisesRegex(ValueError, 'administration'): validate(c)

class WorkloadBindingTests(unittest.TestCase):
    def test_export_filters_state_and_preserves_provider_binding(self):
        from scripts.workload_identity import bindings
        for provider in ('aws', 'azure'):
            c = WorkloadIdentityConfigTests().config(provider)
            annotations = ({'eks.amazonaws.com/role-arn': 'arn:aws:iam::' + c['aws']['account_id'] + ':role/reader'}
                           if provider == 'aws' else {'azure.workload.identity/client-id': '11111111-2222-3333-4444-555555555555'})
            value = {'reader': {'provider': provider, 'subject': 'system:serviceaccount:application:reader',
                     'service_account': {'metadata': {'name': 'reader', 'namespace': 'application', 'annotations': annotations}},
                     'secret': 'SECRET_SENTINEL'}}
            state = {'outputs': {'workload_identity_bindings': {'value': value}, 'private': {'value': 'SECRET_SENTINEL'}}}
            output = bindings(c, state)
            self.assertNotIn('SECRET_SENTINEL', str(output))
            self.assertFalse(output['reader']['service_account']['automountServiceAccountToken'])
            self.assertEqual(output['reader']['pod_labels'], {} if provider == 'aws' else {'azure.workload.identity/use': 'true'})
            value['reader']['subject'] = 'system:serviceaccount:other:reader'
            with self.assertRaisesRegex(ValueError, 'binding'): bindings(c, state)
        with self.assertRaisesRegex(ValueError, 'differ'): bindings(c, {})

    def test_export_rejects_other_account_or_invalid_client(self):
        from scripts.workload_identity import bindings
        for provider in ('aws', 'azure'):
            c = WorkloadIdentityConfigTests().config(provider)
            annotations = ({'eks.amazonaws.com/role-arn': 'arn:aws:iam::999999999999:role/reader'}
                           if provider == 'aws' else {'azure.workload.identity/client-id': 'SECRET_SENTINEL'})
            state = {'outputs': {'workload_identity_bindings': {'value': {'reader': {
                'provider': provider, 'subject': 'system:serviceaccount:application:reader',
                'service_account': {'metadata': {'name': 'reader', 'namespace': 'application', 'annotations': annotations}},
            }}}}}
            with self.assertRaises(ValueError) as error: bindings(c, state)
            self.assertNotIn('SECRET_SENTINEL', str(error.exception))


if __name__ == '__main__':
    unittest.main()
