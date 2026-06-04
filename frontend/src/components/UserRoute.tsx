import { Navigate, Outlet } from "react-router-dom";

import { authStorage } from "../api/client";
import { api } from "../api";

const UserRoute = () => {
  const token = authStorage.getToken();
  const currentUser = api.auth.getCurrentUser();

  if (!token) {
    return <Navigate to="/auth" replace />;
  }

  if (currentUser?.role === "ADMIN") {
    return <Navigate to="/admin" replace />;
  }

  return <Outlet />;
};

export default UserRoute;

