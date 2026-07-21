---
Task ID: 1
Agent: Main
Task: Fix OTP login flow - "invalid username and password" error and secure OTP backend

Work Log:
- Diagnosed root cause: OTPEmailSerializer only checked email existence, not password
- Frontend sent OTP with email only, then made separate LoginView call that failed
- Modified OTPEmailSerializer to require email + password, validate credentials before sending OTP
- Modified OTPVerifySerializer to look up user and check account status after OTP verified
- Modified OTPVerifyView to issue JWT tokens directly (no separate login call needed)
- Updated authService.sendLoginOTP to include password parameter
- Updated authService.verifyLoginOTP to return JWT tokens from backend
- Updated LoginPage Step 1 to show email + password fields
- Updated LoginPage Step 2 to show OTP only (credentials already verified)
- Added loginWithTokens method to AuthContext
- Pushed both backend (ffe6437c) and frontend (36af4f8e) to GitHub

Stage Summary:
- Backend: security/serializers.py and security/views.py updated
- Frontend: authService.js, AuthContext.js, LoginPage.js updated
- New login flow: email+password -> backend validates -> sends OTP -> user enters OTP -> backend issues JWT
- No more "invalid username and password" error since credentials are validated before OTP
---
