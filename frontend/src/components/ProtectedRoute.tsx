import { Navigate, Outlet } from "react-router-dom";
import { authStorage } from "../api/client";

const ProtectedRoute = () => {
  const token = authStorage.getToken();
  return token ? <Outlet /> : <Navigate to="/auth" replace />;
};

export default ProtectedRoute;
