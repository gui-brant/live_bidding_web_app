import { Navigate, Outlet } from "react-router-dom";

import { authStorage } from "../api/client";
import { api } from "../api";

const AdminRoute = () => {
  const token = authStorage.getToken();
  const currentUser = api.auth.getCurrentUser();

  if (!token) {
    return <Navigate to="/auth" replace />;
  }

  if (!currentUser || currentUser.role !== "ADMIN") {
    return <Navigate to="/dashboard" replace />;
  }

  return <Outlet />;
};

export default AdminRoute;

