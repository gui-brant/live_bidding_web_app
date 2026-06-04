import pytest
from conftest import auth_header


# POST /users
class TestCreateUser:
    def test_create_user_success(self, client, create_user):
        payload = {
            "name": "TestCreate",
            "email": "test_create@whatever.com",
            "role": "rep",
        }
        resp = create_user(payload)

        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "TestCreate"
        assert body["email"] == "test_create@whatever.com"
        assert body["role"] == "rep"
        assert body["balance_committed"] is False
        assert body["has_bid"] is False
        assert body["_id"] != ""

    def test_create_user_duplicate_email(self, client, create_user):
        payload = {
            "name": "dup_test",
            "email": "dup_test@whatever.com",
            "role": "rep",
        }
        # initial creation
        resp1 = create_user(payload)
        assert resp1.status_code == 201

        # duplicate creation
        resp2 = create_user({**payload, "name": "dup2"})
        assert resp2.status_code == 409
        # check if the error message mentions the email problem
        assert "email" in resp2.json()["detail"].lower()


# GET /users/me
class TestReadUser:
    def test_read_user_success(self, client, create_user):
        resp = create_user({
            "name": "ReadUserTest",
            "email": "read_user_test@whatever.com",
            "role": "rep",
        })
        assert resp.status_code == 201
        user_id = resp.json()["_id"]

        resp = client.get("/users/me", headers=auth_header(user_id))
        assert resp.status_code == 200
        body = resp.json()
        assert body["_id"] == user_id
        assert body["name"] == "ReadUserTest"
        assert body["email"] == "read_user_test@whatever.com"

    def test_read_user_no_auth(self, client):
        resp = client.get("/users/me")
        assert resp.status_code == 401


# DELETE /users/me
class TestDeleteUser:
    def test_delete_user_success(self, client, create_user):
        resp = create_user({
            "name": "DeleteMe",
            "email": "deleteme_test@example.com",
            "role": "rep",
        })
        assert resp.status_code == 201
        user_id = resp.json()["_id"]

        resp = client.delete("/users/me", headers=auth_header(user_id))
        assert resp.status_code == 204

        # Confirm the user is gone
        resp = client.get("/users/me", headers=auth_header(user_id))
        assert resp.status_code == 401  # user no longer exists

    def test_delete_user_not_found(self, client):
        # use a valid-format but nonexistent ObjectId
        from bson import ObjectId
        fake_id = str(ObjectId())
        resp = client.delete("/users/me", headers=auth_header(fake_id))
        assert resp.status_code == 401


# PATCH /users/me
class TestUpdateUser:
    def test_update_name(self, client, create_user):
        resp = create_user({
            "name": "OldName",
            "email": "update_test@example.com",
            "role": "rep",
        })
        assert resp.status_code == 201
        user_id = resp.json()["_id"]

        resp = client.patch(
            "/users/me",
            json={"name": "NewName"},
            headers=auth_header(user_id),
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "NewName"

    def test_update_empty_payload(self, client, create_user):
        resp = create_user({
            "name": "EmptyPatch",
            "email": "emptypatch_test@example.com",
            "role": "rep",
        })
        assert resp.status_code == 201
        user_id = resp.json()["_id"]

        resp = client.patch(
            "/users/me",
            json={},
            headers=auth_header(user_id),
        )
        assert resp.status_code == 400
        assert "no updates" in resp.json()["detail"].lower()

    def test_update_duplicate_email(self, client, create_user):
        # Create two users
        resp1 = create_user({
            "name": "User1",
            "email": "user1_dup_test@example.com",
            "role": "rep",
        })
        assert resp1.status_code == 201

        resp2 = create_user({
            "name": "User2",
            "email": "user2_dup_test@example.com",
            "role": "rep",
        })
        assert resp2.status_code == 201
        user2_id = resp2.json()["_id"]

        # Try to update user2's email to user1's email
        resp = client.patch(
            "/users/me",
            json={"email": "user1_dup_test@example.com"},
            headers=auth_header(user2_id),
        )
        assert resp.status_code == 409
        assert "email" in resp.json()["detail"].lower()
