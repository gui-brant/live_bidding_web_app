import { Navigate, Route, Routes } from "react-router-dom";

import ProtectedRoute from "../components/ProtectedRoute";
import RootLayout from "./RootLayout";
import AuthPage from "../pages/AuthPage";
import Dashboard from "./pages/Dashboard";
import Settings from "./pages/Settings";
import Auctions from "./pages/Auctions";
import BiddingRoom from "./pages/BiddingRoom";
import Wishlist from "./pages/Wishlist";
import AdminRoute from "../components/AdminRoute";
import AdminOverview from "./pages/admin/AdminOverview";
import AdminAuctions from "./pages/admin/AdminAuctions";
import AdminPastAuctions from "./pages/admin/AdminPastAuctions";
import AdminUsers from "./pages/admin/AdminUsers";
import AdminKogbucks from "./pages/admin/AdminKogbucks";
import AdminItems from "./pages/admin/AdminItems";
import AdminBiddingRoom from "./pages/admin/AdminBiddingRoom";
import AdminWishlist from "./pages/admin/AdminWishlist";
import UserRoute from "../components/UserRoute";

const App = () => {
  return (
    <Routes>
      <Route path="/auth" element={<AuthPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<RootLayout />}>
          <Route element={<UserRoute />}>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/wishlist" element={<Wishlist />} />
            <Route path="/auctions" element={<Auctions />} />
            <Route path="/bidding/:auctionId" element={<BiddingRoom />} />
          </Route>
          <Route element={<AdminRoute />}>
            <Route path="/admin" element={<AdminOverview />} />
            <Route path="/admin/auctions" element={<AdminAuctions />} />
            <Route path="/admin/auctions/past" element={<AdminPastAuctions />} />
            <Route path="/admin/bidding/:auctionId" element={<AdminBiddingRoom />} />
            <Route path="/admin/items" element={<AdminItems />} />
            <Route path="/admin/users" element={<AdminUsers />} />
            <Route path="/admin/kogbucks" element={<AdminKogbucks />} />
            <Route path="/admin/wishlist" element={<AdminWishlist />} />
          </Route>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/auth" replace />} />
    </Routes>
  );
};

export default App;
