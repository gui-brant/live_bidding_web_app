import { NavLink, useNavigate } from "react-router-dom";

import { authStorage } from "../api/client";
import { api } from "../api";

const NavBar = () => {
  const navigate = useNavigate();
  const token = authStorage.getToken();
  const currentUser = api.auth.getCurrentUser();
  const isAdmin = currentUser?.role === "ADMIN";

  const handleLogout = () => {
    api.auth.logout();
    navigate("/auth");
  };

  return (
    <nav className="nav-bar">
      <div className="nav-brand">SE3350</div>
      <div className="nav-links">
        {token ? (
          isAdmin ? (
            <>
              <NavLink to="/admin" className={({ isActive }) => (isActive ? "active" : "")}>
                Admin Overview
              </NavLink>
              <NavLink to="/admin/auctions" className={({ isActive }) => (isActive ? "active" : "")}>
                Admin Auctions
              </NavLink>
              <NavLink to="/admin/items" className={({ isActive }) => (isActive ? "active" : "")}>
                Admin Items
              </NavLink>
              <NavLink to="/admin/users" className={({ isActive }) => (isActive ? "active" : "")}>
                Admin Users
              </NavLink>
              <NavLink to="/admin/kogbucks" className={({ isActive }) => (isActive ? "active" : "")}>
                Admin Kogbucks
              </NavLink>
              <NavLink to="/admin/wishlist" className={({ isActive }) => (isActive ? "active" : "")}>
                Wishlist
              </NavLink>
              <button type="button" className="link-button" onClick={handleLogout}>
                Logout
              </button>
            </>
          ) : (
            <>
              <NavLink to="/dashboard" className={({ isActive }) => (isActive ? "active" : "")}>
                Dashboard
              </NavLink>
              <NavLink to="/auctions" className={({ isActive }) => (isActive ? "active" : "")}>
                Auctions
              </NavLink>
              <NavLink to="/wishlist" className={({ isActive }) => (isActive ? "active" : "")}>
                Wishlist
              </NavLink>
              <NavLink to="/settings" className={({ isActive }) => (isActive ? "active" : "")}>
                Settings
              </NavLink>
              <button type="button" className="link-button" onClick={handleLogout}>
                Logout
              </button>
            </>
          )
        ) : (
          <NavLink to="/auth" className={({ isActive }) => (isActive ? "active" : "")}>
            Auth
          </NavLink>
        )}
      </div>
    </nav>
  );
};

export default NavBar;
