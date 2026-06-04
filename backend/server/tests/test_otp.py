"""
IMPORTANT: Requires AUTH_DEV_MODE=true set on the server
"""

class TestOtpEndpoints:
    def test_request_otp_success(self, client):
        email = "test_otp@example.com"
        resp = client.post("/auth/otp/request", json={"email": email})
        assert resp.status_code == 204

    def test_otp_verification_flow_success(self, client):
        email = "verify_success@example.com"
        
        # request otp
        resp = client.post("/auth/otp/request", json={"email": email})
        assert resp.status_code == 204
        
        # get the otp from the endpoint with AUTH_DEV_MODE=true
        dev_resp = client.get(f"/dev/otp/{email}")
        assert dev_resp.status_code == 200, "AUTH_DEV_MODE=true must be enabled on the server for this test to pass."
        code = dev_resp.json()["code"]
        
        # verify the otp
        verify_resp = client.post("/auth/otp/verify", json={"email": email, "code": code})
        assert verify_resp.status_code == 200
        
        body = verify_resp.json()
        assert "access_token" in body
        assert body["profile"]["email"] == email

    def test_otp_verification_invalid_code(self, client):
        email = "invalid_code@example.com"
        
        # get otp
        client.post("/auth/otp/request", json={"email": email})
        
        # verify with a bad code
        verify_resp = client.post("/auth/otp/verify", json={"email": email, "code": "000000"})
        assert verify_resp.status_code == 401
        assert verify_resp.json()["code"] == "OTP_INVALID"

    def test_otp_verification_expired_or_nonexistent(self, client):
        # Try to verify for an email that never requested OTP
        email = "no_otp@example.com"
        verify_resp = client.post("/auth/otp/verify", json={"email": email, "code": "123456"})
        assert verify_resp.status_code == 401
        assert verify_resp.json()["code"] == "OTP_INVALID"

    def test_logout_success(self, client):
        email = "logout_test@example.com"
        
        # get a token
        client.post("/auth/otp/request", json={"email": email})
        dev_resp = client.get(f"/dev/otp/{email}")
        code = dev_resp.json()["code"]
        verify_resp = client.post("/auth/otp/verify", json={"email": email, "code": code})
        token = verify_resp.json()["access_token"]
        
        # logout
        logout_resp = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
        assert logout_resp.status_code == 204
