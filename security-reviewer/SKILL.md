# OWASP Top 10 Security Reviewer

This skill is designed to perform a comprehensive security code review based on the OWASP Top 10 vulnerabilities. Use this skill when the user asks for a security audit, code review for vulnerabilities, or specifically mentions OWASP.

## Core Mandates

1.  **Prioritize Critical Vulnerabilities:** Focus on high-impact issues that could lead to data breaches or system compromise.
2.  **Context-Aware Analysis:** Understand the language, framework, and deployment context to identify relevant threats (e.g., SQL injection is relevant for SQL databases, XSS for web frontends).
3.  **Actionable Remediation:** Provide clear, specific code examples or configuration changes to fix identified issues.
4.  **No False Positives:** Verify findings to the best of your ability. If unsure, mark as "Potential" or "Requires Manual Verification".

## OWASP Top 10 Checklist

When reviewing code, systematically check for the following categories:

1.  **A01:2021-Broken Access Control**
    *   Check for missing authorization checks (e.g., `is_admin`, `has_permission`).
    *   Look for Insecure Direct Object References (IDOR) - exposing internal IDs in URLs/APIs without validation.
    *   Verify that restricted pages/endpoints are protected.

2.  **A02:2021-Cryptographic Failures**
    *   Identify hardcoded secrets (API keys, passwords, tokens).
    *   Check for weak encryption algorithms (e.g., MD5, SHA1, DES).
    *   Ensure sensitive data (PII, passwords) is not stored or transmitted in plain text.
    *   Verify proper use of random number generators (CSPRNG).

3.  **A03:2021-Injection**
    *   **SQL Injection:** Look for string concatenation in SQL queries. Ensure parameterized queries or ORMs are used correctly.
    *   **Command Injection:** Check for user input being passed to system commands (e.g., `os.system`, `exec`).
    *   **LDAP/NoSQL Injection:** Verify input sanitization for other data stores.

4.  **A04:2021-Insecure Design**
    *   Assess if the architecture inherently supports security (e.g., threat modeling).
    *   Look for lack of rate limiting or anti-automation defenses.

5.  **A05:2021-Security Misconfiguration**
    *   Check for default credentials or configurations.
    *   Look for verbose error messages exposing stack traces to users.
    *   Verify security headers (CSP, HSTS, X-Frame-Options).
    *   Check for unnecessary features or services enabled.

6.  **A06:2021-Vulnerable and Outdated Components**
    *   Check `package.json`, `requirements.txt`, etc., for known vulnerable dependencies (if version info is available).
    *   Advise on updating dependencies.

7.  **A07:2021-Identification and Authentication Failures**
    *   Check for weak password policies.
    *   Verify session management (timeouts, secure cookies).
    *   Look for lack of multi-factor authentication (MFA) support where appropriate.

8.  **A08:2021-Software and Data Integrity Failures**
    *   Verify code signing or integrity checks for updates/plugins.
    *   Check for insecure deserialization vulnerabilities (e.g., `pickle.load` in Python, `ObjectInputStream` in Java) with untrusted data.

9.  **A09:2021-Security Logging and Monitoring Failures**
    *   Ensure critical events (logins, failed access, errors) are logged.
    *   Verify logs do not contain sensitive data.

10. **A10:2021-Server-Side Request Forgery (SSRF)**
    *   Check if user-supplied URLs are fetched by the server without validation (allowlisting).

## Review Process & Output Format

1.  **Analyze:** Read the provided code thoroughly.
2.  **Identify:** Match patterns to the OWASP categories above.
3.  **Report:** specific findings using the format below.

### Output Format

```markdown
## Security Review Report (OWASP Top 10)

### Summary
[Brief overview of the security posture of the reviewed code.]

### Findings

#### [High/Medium/Low] <Vulnerability Name> (OWASP Category)
*   **Location:** `path/to/file:line_number`
*   **Description:** [Explain why this is a vulnerability.]
*   **Remediation:** [Provide code fix or specific instruction.]
    ```language
    // Secure code example
    ```

... (Repeat for other findings)

### General Recommendations
*   [Broader security advice not tied to a specific line of code]
```
