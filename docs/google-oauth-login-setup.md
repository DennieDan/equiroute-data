# JalanLens Google OAuth setup handoff

Use this to finish the **Continue with Google** login flow for public users.

## Current frontend state

- Login page: `login/index.html`
- Supabase project URL: `https://khddsjemkdcgumfvkraa.supabase.co`
- The frontend now calls Supabase OAuth:
  ```js
  supabase.auth.signInWithOAuth({ provider: "google", options: { redirectTo } })
  ```
- OAuth callback returns to:
  ```txt
  https://equiroute.online/login/?oauth=public
  ```
- After callback, `finishGoogleLogin()` reads `supabase.auth.getSession()`, creates/upserts a public `app_users` row, stores `jalanlens_user`, then redirects into the app.

## Step-by-step setup

### 1. Google Cloud: create/select project

1. Open Google Cloud Console:
   https://console.cloud.google.com/
2. Create or select the JalanLens / Tech4City project.
3. Go to **APIs & Services → OAuth consent screen**.
4. Configure app basics:
   - App name: `JalanLens`
   - User support email: teammate/team email
   - Developer contact email: teammate/team email
5. Set publishing status:
   - For quick hackathon testing: keep **Testing** and add test users.
   - Before final demo/public use: publish **In production**.

### 2. Google Cloud: create OAuth Web client

1. Go to **APIs & Services → Credentials**.
2. Click **Create Credentials → OAuth client ID**.
3. Application type: **Web application**.
4. Name: `JalanLens Supabase Auth`.
5. Add Authorized JavaScript origins:
   ```txt
   https://equiroute.online
   http://localhost:8088
   http://127.0.0.1:8088
   ```
6. Add Authorized redirect URIs:
   ```txt
   https://khddsjemkdcgumfvkraa.supabase.co/auth/v1/callback
   ```
7. Create the client.
8. Copy the **Client ID** and **Client secret**.

### 3. Supabase: enable Google provider

1. Open Supabase dashboard for project `khddsjemkdcgumfvkraa`.
2. Go to **Authentication → Providers → Google**.
3. Enable Google.
4. Paste:
   - Google Client ID
   - Google Client Secret
5. Save.

### 4. Supabase: set URL configuration

Go to **Authentication → URL Configuration**.

Set **Site URL**:
```txt
https://equiroute.online
```

Add Redirect URLs:
```txt
https://equiroute.online/login/
https://equiroute.online/login/?oauth=public
https://equiroute.online/street-intelligence/
http://localhost:8088/login/
http://127.0.0.1:8088/login/
```

Save changes.

### 5. Verify the live flow

1. Open:
   ```txt
   https://equiroute.online/login/?next=/street-intelligence/
   ```
2. Click **Continue with Google**.
3. Choose a Google account.
4. It should redirect back to:
   ```txt
   https://equiroute.online/login/?oauth=public&next=/street-intelligence/
   ```
5. Then it should enter the app.
6. In DevTools console, verify:
   ```js
   JSON.parse(localStorage.getItem("jalanlens_user"))
   ```
   Expected:
   - `role` is `public`
   - `metadata.google_oauth` is `true`
   - `username` is the Google email

### 6. If it fails

- If Google says `redirect_uri_mismatch`, check the Google Cloud redirect URI exactly matches:
  ```txt
  https://khddsjemkdcgumfvkraa.supabase.co/auth/v1/callback
  ```
- If Supabase says provider is disabled, re-check **Authentication → Providers → Google**.
- If callback works but app user save fails, check `app_users` columns include the newer fields used by login:
  - `auth_user_id`
  - `username`
  - `public_persona_type`
  - `demographic_profile`
- If GitHub Pages looks stale, open with cache busting:
  ```txt
  https://equiroute.online/login/?v=latest
  ```

## Notes

- Google OAuth is currently intended for **public users** only.
- Authority users should keep username/password login unless the team decides to add authority SSO later.
- Do not commit Google Client Secret into the repo.
