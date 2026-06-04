import { useEffect, useRef } from "react";
import { Outlet, useNavigate } from "react-router-dom";

import { api } from "../api";
import NavBar from "../components/NavBar";
import PageTransition from "../components/PageTransition";

const INACTIVITY_TIMEOUT_MS = 1800000;

const RootLayout = () => {
  const navigate = useNavigate();
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    const resetTimer = () => {
      if (timerRef.current) {
        window.clearTimeout(timerRef.current);
      }
      timerRef.current = window.setTimeout(async () => {
        try {
          await api.auth.logout();
        } catch (error) {
          console.warn("Logout failed, clearing session locally.", error);
        } finally {
          navigate("/auth", { replace: true });
        }
      }, INACTIVITY_TIMEOUT_MS);
    };

    const events: Array<keyof WindowEventMap> = [
      "mousemove",
      "keydown",
      "click",
      "scroll",
      "touchstart"
    ];

    events.forEach((eventName) => window.addEventListener(eventName, resetTimer, { passive: true }));
    resetTimer();

    return () => {
      events.forEach((eventName) => window.removeEventListener(eventName, resetTimer));
      if (timerRef.current) {
        window.clearTimeout(timerRef.current);
      }
    };
  }, [navigate]);

  return (
    <div className="app-shell">
      <NavBar />
      <main className="app-main">
        <PageTransition>
          <Outlet />
        </PageTransition>
      </main>
    </div>
  );
};

export default RootLayout;
