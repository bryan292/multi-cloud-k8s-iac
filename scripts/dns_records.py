"""Exact record selection for isolated ExternalDNS integration-test cleanup."""
def records_for_test(aws, zone, hostname, include_ownership=False):
    names = [hostname]
    if include_ownership:
        names += [prefix + hostname for prefix in ['a-', 'aaaa-', 'cname-']]
    found = {}
    for name in names:
        result = aws('route53', 'list-resource-record-sets', '--hosted-zone-id', zone,
                     '--start-record-name', name, '--max-items', '10')
        for record in result['ResourceRecordSets']:
            if record['Name'].rstrip('.') == name:
                found[(record['Name'], record['Type'])] = record
    return list(found.values())
