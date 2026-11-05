# Security model

## Supported scope

Veritaserum currently supports a trusted, single-host localhost deployment using synthetic incident evidence. The HTTP service does not expose arbitrary commands or production actions. Execution changes only the built-in checkout simulator.

## Enforced boundaries

- Authenticated active membership gates every room read and mutation. Private document/proposal reads additionally require ownership.
- Only an owner can release an exact, validated statement. Source revisions are checked at approval time; shared inference receives released facts rather than source documents.
- Role checks, current room revisions, and active disclosures are checked again at execution. Failed checks do not commit simulator changes. Executing the same plan again does not repeat its effect.
- HTTP protections include CSRF/origin and Host validation, HttpOnly/SameSite cookies, bounded request bodies, no-store responses, and a static-file allowlist.
- In-flight model calls are deduplicated per investigation/worker within one server process. Provider errors fail closed rather than silently substituting a reference answer.

## Trust and limitations

The server administrator, operating system, local database, and configured model providers are trusted. Data is not encrypted at rest. Private model calls send that owner’s evidence to the configured provider; provider retention and training policies are external to this application. Approved statements can themselves contain or imply sensitive information. Withdrawal and access removal cannot retract information already seen or copied.

Sample accounts have public passwords. Loopback binding is not a substitute for production identity, transport security, quotas, encrypted backups, durable jobs, or independent security assessment. Do not expose this service to the Internet or load sensitive company records as if those protections were implemented.

## Reporting

Do not post credentials, private source notes, or exploit details containing sensitive data in public issues. Public issues may describe non-sensitive bugs with synthetic reproductions. For a sensitive vulnerability, first contact the repository owner to arrange a private reporting channel. No security audit or privacy certification is claimed.
