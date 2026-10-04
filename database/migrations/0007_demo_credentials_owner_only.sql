-- 0007 · Demo credentials live only in the database, readable only by the owner.
--
-- The app no longer exposes a persona roster, the demo password, activation codes or live
-- authenticator codes. For the demo, open pgAdmin on the OWNER connection and run:
--     SELECT * FROM demo.credentials;
-- The current 6-digit authenticator code is computed right here, in SQL (RFC 6238 TOTP).

ALTER TABLE demo.personas ADD COLUMN demo_password text, ADD COLUMN totp_secret text;
COMMENT ON COLUMN demo.personas.totp_secret IS 'Demo only: base32 authenticator secret so demo.credentials can show the current code.';

CREATE FUNCTION demo.base32_decode(s text) RETURNS bytea
LANGUAGE plpgsql IMMUTABLE STRICT AS $$
DECLARE
  alphabet text := 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  bits text := '';
  result bytea := '';
  v int;
BEGIN
  FOR i IN 1..length(s) LOOP
    v := position(substr(upper(s), i, 1) IN alphabet) - 1;
    CONTINUE WHEN v < 0;
    bits := bits || v::bit(5)::text;
  END LOOP;
  FOR i IN 0..(length(bits) / 8 - 1) LOOP
    result := result || set_byte('\x00'::bytea, 0, substr(bits, i * 8 + 1, 8)::bit(8)::int);
  END LOOP;
  RETURN result;
END $$;

-- RFC 6238: HMAC-SHA1 over the 30-second counter, dynamic truncation, 6 digits.
CREATE OR REPLACE FUNCTION demo.totp(secret text, at timestamptz DEFAULT now()) RETURNS text
LANGUAGE plpgsql STABLE STRICT AS $$  -- STRICT: no secret → NULL
DECLARE
  h bytea := public.hmac(int8send(floor(extract(epoch FROM at) / 30)::bigint), demo.base32_decode(secret), 'sha1');
  o int := get_byte(h, 19) & 15;
BEGIN
  -- Postgres gives all bitwise operators equal precedence, so every term is bracketed
  RETURN lpad(((((get_byte(h, o) & 127) << 24) | (get_byte(h, o + 1) << 16) | (get_byte(h, o + 2) << 8) | get_byte(h, o + 3)) % 1000000)::text, 6, '0');
END $$;

CREATE VIEW demo.credentials AS
SELECT p.sort, u.full_name, r.title AS role, u.status, u.email, u.phone,
       CASE WHEN u.status = 'ACTIVE' THEN p.demo_password END AS password,
       CASE WHEN u.status = 'INVITED' THEN p.activation_code END AS activation_code,
       CASE WHEN u.status = 'ACTIVE' THEN demo.totp(p.totp_secret) END AS authenticator_code_now,
       30 - (floor(extract(epoch FROM now()))::int % 30) AS seconds_left,
       p.headline
FROM demo.personas p
JOIN iam.users u ON u.id = p.user_id
JOIN iam.roles r ON r.code = u.role_code
ORDER BY p.sort;
COMMENT ON VIEW demo.credentials IS 'Demo sign-in details incl. the live authenticator code. Owner only — not visible to the app or the read-only role.';

-- The app may write demo rows while seeding, but never read them back. Read-only sees nothing.
REVOKE ALL ON demo.personas FROM cfv_app, cfv_readonly;
GRANT INSERT ON demo.personas TO cfv_app;
