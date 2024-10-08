import boto3
import dns.resolver
import re

# Initialize the Route 53 client
client = boto3.client('route53')

# Function to check if an IP is public
def is_public_ip(ip):
    # Regex to match private IP ranges (10.x.x.x, 172.16.x.x - 172.31.x.x, 192.168.x.x)
    private_ip_patterns = [
        r"^10\.",
        r"^172\.(1[6-9]|2[0-9]|3[01])\.",
        r"^192\.168\."
    ]
    for pattern in private_ip_patterns:
        if re.match(pattern, ip):
            return False  # Private IP
    return True  # Public IP

# Function to resolve DNS names using dnspython
def resolve_dns_with_dnspython(name):
    ips = []
    try:
        # Resolve A records
        answer = dns.resolver.resolve(name, 'A')
        for ip in answer:
            ips.append(ip.to_text())
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
        pass  # No A records found

    try:
        # Resolve CNAME records (and follow them to the A record)
        cname_answer = dns.resolver.resolve(name, 'CNAME')
        for cname in cname_answer:
            # Recursively resolve the CNAME target
            ips += resolve_dns_with_dnspython(cname.target.to_text())
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
        pass  # No CNAME records found

    return ips

# Step 1: Get all public hosted zones
def get_public_hosted_zones():
    response = client.list_hosted_zones()
    public_zones = [zone['Id'].split('/')[-1] for zone in response['HostedZones'] if not zone['Config']['PrivateZone']]
    return public_zones

# Step 2: Get A and CNAME records from a hosted zone
def get_a_and_cname_records(zone_id):
    paginator = client.get_paginator('list_resource_record_sets')
    records = []
    for page in paginator.paginate(HostedZoneId=zone_id):
        for record in page['ResourceRecordSets']:
            if record['Type'] in ['A', 'CNAME']:
                records.append(record)
    return records

# Step 3: Process records and filter only public IPs
def process_records(records):
    results = []
    for record in records:
        name = record['Name']
        record_type = record['Type']

        # Handle A records
        if record_type == 'A':
            if 'AliasTarget' in record:
                # It's an alias record, resolve the alias target
                alias_target = record['AliasTarget']['DNSName']
                resolved_ips = resolve_dns_with_dnspython(alias_target)
            else:
                # It's a regular A record with IP addresses
                resolved_ips = [ip['Value'] for ip in record['ResourceRecords']]

        # Handle CNAME records
        elif record_type == 'CNAME':
            cname_target = record['ResourceRecords'][0]['Value']
            resolved_ips = resolve_dns_with_dnspython(cname_target)

        # Filter and keep only public IPs
        public_ips = [ip for ip in resolved_ips if is_public_ip(ip)]
        if public_ips:
            for ip in public_ips:
                results.append({'Name': name, 'IP': ip})
    
    return results

# Step 4: Main function to execute the entire process
def main():
    print("name,public_ip")
    
    public_zones = get_public_hosted_zones()
    for zone_id in public_zones:
        records = get_a_and_cname_records(zone_id)
        if not records:
            continue  # Skip zones with no relevant records

        public_records = process_records(records)
        for record in public_records:
            print(f"{record['Name']},{record['IP']}")

if __name__ == "__main__":
    main()
