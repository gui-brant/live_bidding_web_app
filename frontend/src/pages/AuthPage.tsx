import { FormEvent, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api";
import type { RegisterPayload, UserRole } from "../api/types";
import Button from "../components/Button";
import Card from "../components/Card";

const ALLOW_ADMIN_REGISTER = true;

type LoginFields = {
  email: string;
  otp: string;
};

type RegisterFields = {
  email: string;
  displayName: string;
  role: UserRole;
  otp: string;
};

type FieldErrors<T> = Partial<Record<keyof T, string>>;

type ActiveTab = "login" | "register";

type LoginStep = "request" | "verify";

type RegisterStep = "request" | "verify";

const AuthPage = () => {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<ActiveTab>("login");
  const [loginStep, setLoginStep] = useState<LoginStep>("request");
  const [registerStep, setRegisterStep] = useState<RegisterStep>("request");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [loginFields, setLoginFields] = useState<LoginFields>({
    email: "",
    otp: ""
  });
  const [registerFields, setRegisterFields] = useState<RegisterFields>({
    email: "",
    displayName: "",
    role: "REP",
    otp: ""
  });
  const [loginErrors, setLoginErrors] = useState<FieldErrors<LoginFields>>({});
  const [registerErrors, setRegisterErrors] = useState<FieldErrors<RegisterFields>>({});
  const [devOtp, setDevOtp] = useState<string | null>(null);
  const [otpExpiresAt, setOtpExpiresAt] = useState<number | null>(null);
  const [otpCountdown, setOtpCountdown] = useState<string>("");

  useEffect(() => {
    api.auth.initMockUsersIfNeeded();
  }, []);

  useEffect(() => {
    if (!otpExpiresAt) {
      setOtpCountdown("");
      return;
    }
    const interval = window.setInterval(() => {
      const remainingMs = otpExpiresAt - Date.now();
      if (remainingMs <= 0) {
        setOtpCountdown("Expired");
        return;
      }
      const minutes = Math.floor(remainingMs / 60000);
      const seconds = Math.floor((remainingMs % 60000) / 1000);
      setOtpCountdown(`${minutes}:${seconds.toString().padStart(2, "0")}`);
    }, 500);

    return () => window.clearInterval(interval);
  }, [otpExpiresAt]);

  const canSelectAdmin = useMemo(() => {
    return ALLOW_ADMIN_REGISTER || registerFields.email.trim().toLowerCase() === "admin@example.com";
  }, [registerFields.email]);

  const resetMessages = () => {
    setFormError(null);
    setSuccessMessage(null);
  };

  const resetLoginState = () => {
    setLoginErrors({});
    setLoginFields({ email: "", otp: "" });
    setLoginStep("request");
    setDevOtp(null);
    setOtpExpiresAt(null);
  };

  const resetRegisterState = () => {
    setRegisterErrors({});
    setRegisterFields({ email: "", displayName: "", role: "REP", otp: "" });
    setRegisterStep("request");
    setDevOtp(null);
    setOtpExpiresAt(null);
  };

  const handleTabChange = (tab: ActiveTab) => {
    setActiveTab(tab);
    resetMessages();
    if (tab === "login") {
      resetLoginState();
    } else {
      resetRegisterState();
    }
  };

  const validateLoginRequest = (): boolean => {
    const errors: FieldErrors<LoginFields> = {};
    if (!loginFields.email.trim()) {
      errors.email = "Email is required";
    }
    setLoginErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const validateLoginVerify = (): boolean => {
    const errors: FieldErrors<LoginFields> = {};
    if (!loginFields.otp.trim()) {
      errors.otp = "OTP is required";
    }
    setLoginErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const validateRegisterRequest = (): boolean => {
    const errors: FieldErrors<RegisterFields> = {};
    if (!registerFields.email.trim()) {
      errors.email = "Email is required";
    }
    setRegisterErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const validateRegisterVerify = (): boolean => {
    const errors: FieldErrors<RegisterFields> = {};
    if (!registerFields.otp.trim()) {
      errors.otp = "OTP is required";
    }
    setRegisterErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleRequestOtpLogin = async (event: FormEvent) => {
    event.preventDefault();
    resetMessages();
    if (!validateLoginRequest()) {
      return;
    }
    setIsSubmitting(true);
    try {
      const response = await api.auth.requestOtp(loginFields.email.trim(), "LOGIN");
      setDevOtp(response.otp_dev ?? null);
      setOtpExpiresAt(response.expires_at);
      setLoginStep("verify");
    } catch (error) {
      let message = error instanceof Error ? error.message : "Failed to send OTP";
      if (message.includes("409")) {
        message = "Account already exists. Please log in.";
      }
      setFormError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleVerifyOtpLogin = async (event: FormEvent) => {
    event.preventDefault();
    resetMessages();
    if (!validateLoginVerify()) {
      return;
    }
    setIsSubmitting(true);
    try {
      await api.auth.verifyOtp(loginFields.email.trim(), loginFields.otp.trim(), "LOGIN");
      navigate("/dashboard");
    } catch (error) {
      const message = error instanceof Error ? error.message : "OTP verification failed";
      setFormError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleResendOtpLogin = async () => {
    resetMessages();
    setIsSubmitting(true);
    try {
      const response = await api.auth.requestOtp(loginFields.email.trim(), "LOGIN");
      setDevOtp(response.otp_dev ?? null);
      setOtpExpiresAt(response.expires_at);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to resend OTP";
      setFormError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRequestOtpRegister = async (event: FormEvent) => {
    event.preventDefault();
    resetMessages();
    if (!validateRegisterRequest()) {
      return;
    }
    setIsSubmitting(true);
    try {
      const role = canSelectAdmin ? registerFields.role : "REP";
      const name = registerFields.displayName.trim() || registerFields.email.trim();
      await api.users.createUser({
        name,
        email: registerFields.email.trim(),
        role: role === "ADMIN" ? "admin" : "rep",
        balance_amount: 0,
        balance_committed: false,
        has_bid: false
      });
      const payload: RegisterPayload = {
        email: registerFields.email.trim(),
        display_name: registerFields.displayName.trim() || undefined,
        role
      };
      const response = await api.auth.requestOtp(registerFields.email.trim(), "REGISTER", payload);
      setDevOtp(response.otp_dev ?? null);
      setOtpExpiresAt(response.expires_at);
      setRegisterStep("verify");
    } catch (error) {
      let message = error instanceof Error ? error.message : "Failed to send OTP";
      if (message.includes("409") || message.toLowerCase().includes("email already used")) {
        message = "Account already exists. Please log in.";
      }
      setFormError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleVerifyOtpRegister = async (event: FormEvent) => {
    event.preventDefault();
    resetMessages();
    if (!validateRegisterVerify()) {
      return;
    }
    setIsSubmitting(true);
    try {
      await api.auth.verifyOtp(registerFields.email.trim(), registerFields.otp.trim(), "REGISTER");
      navigate("/dashboard");
    } catch (error) {
      const message = error instanceof Error ? error.message : "OTP verification failed";
      setFormError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleResendOtpRegister = async () => {
    resetMessages();
    setIsSubmitting(true);
    try {
      const payload: RegisterPayload = {
        email: registerFields.email.trim(),
        display_name: registerFields.displayName.trim() || undefined,
        role: canSelectAdmin ? registerFields.role : "REP"
      };
      const response = await api.auth.requestOtp(registerFields.email.trim(), "REGISTER", payload);
      setDevOtp(response.otp_dev ?? null);
      setOtpExpiresAt(response.expires_at);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to resend OTP";
      setFormError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section className="page auth-page">
      <Card>
        <div className="auth-header">
          <h1>Welcome</h1>
          <p className="muted">Use the tabs below to sign in or register.</p>
        </div>
        <div className="tabs">
          <button
            type="button"
            className={`tab ${activeTab === "login" ? "active" : ""}`}
            onClick={() => handleTabChange("login")}
          >
            Login
          </button>
          <button
            type="button"
            className={`tab ${activeTab === "register" ? "active" : ""}`}
            onClick={() => handleTabChange("register")}
          >
            Register
          </button>
        </div>

        {formError ? <p className="error">{formError}</p> : null}
        {successMessage ? <p className="success">{successMessage}</p> : null}

        {activeTab === "login" ? (
          <form className="form" onSubmit={loginStep === "request" ? handleRequestOtpLogin : handleVerifyOtpLogin}>
            <div className="step-indicator">
              {loginStep === "request" ? "Step 1: Request OTP" : "Step 2: Verify OTP"}
            </div>
            {loginStep === "request" ? (
              <>
                <label className="field">
                  <span>Email</span>
                  <input
                    type="text"
                    value={loginFields.email}
                    onChange={(event) =>
                      setLoginFields({ ...loginFields, email: event.target.value })
                    }
                  />
                  {loginErrors.email ? (
                    <span className="field-error">{loginErrors.email}</span>
                  ) : null}
                </label>
                <Button type="submit" disabled={isSubmitting}>
                  {isSubmitting ? "Sending..." : "Send OTP to Login"}
                </Button>
              </>
            ) : (
              <>
                <label className="field">
                  <span>Email</span>
                  <input type="text" value={loginFields.email} readOnly />
                </label>
                <label className="field">
                  <span>OTP Code</span>
                  <input
                    type="text"
                    value={loginFields.otp}
                    onChange={(event) =>
                      setLoginFields({ ...loginFields, otp: event.target.value })
                    }
                  />
                  {loginErrors.otp ? <span className="field-error">{loginErrors.otp}</span> : null}
                </label>
                {import.meta.env.DEV && devOtp ? (
                  <div className="dev-banner">DEV OTP (for testing): {devOtp}</div>
                ) : null}
                {otpCountdown ? <p className="muted">Expires in: {otpCountdown}</p> : null}
                <div className="button-row">
                  <Button type="submit" disabled={isSubmitting}>
                    {isSubmitting ? "Verifying..." : "Verify OTP"}
                  </Button>
                  <Button type="button" variant="secondary" disabled={isSubmitting} onClick={handleResendOtpLogin}>
                    Resend OTP
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={isSubmitting}
                    onClick={() => {
                      resetMessages();
                      setLoginStep("request");
                      setLoginFields({ email: "", otp: "" });
                      setDevOtp(null);
                      setOtpExpiresAt(null);
                    }}
                  >
                    Back
                  </Button>
                </div>
              </>
            )}
          </form>
        ) : (
          <form className="form" onSubmit={registerStep === "request" ? handleRequestOtpRegister : handleVerifyOtpRegister}>
            <div className="step-indicator">
              {registerStep === "request" ? "Step 1: Request OTP" : "Step 2: Verify OTP"}
            </div>
            {registerStep === "request" ? (
              <>
                <label className="field">
                  <span>Email</span>
                  <input
                    type="email"
                    value={registerFields.email}
                    onChange={(event) =>
                      setRegisterFields({ ...registerFields, email: event.target.value })
                    }
                  />
                  {registerErrors.email ? (
                    <span className="field-error">{registerErrors.email}</span>
                  ) : null}
                </label>
                <label className="field">
                  <span>Display Name (optional)</span>
                  <input
                    type="text"
                    value={registerFields.displayName}
                    onChange={(event) =>
                      setRegisterFields({ ...registerFields, displayName: event.target.value })
                    }
                  />
                </label>
                <label className="field">
                  <span>Role</span>
                  <select
                    value={registerFields.role}
                    onChange={(event) =>
                      setRegisterFields({
                        ...registerFields,
                        role: event.target.value as UserRole
                      })
                    }
                    disabled={!canSelectAdmin}
                  >
                    <option value="REP">REP</option>
                    {canSelectAdmin ? <option value="ADMIN">ADMIN</option> : null}
                  </select>
                  {!canSelectAdmin ? (
                    <span className="muted">Admin registration is disabled.</span>
                  ) : null}
                </label>
                <Button type="submit" disabled={isSubmitting}>
                  {isSubmitting ? "Sending..." : "Send OTP to Register"}
                </Button>
              </>
            ) : (
              <>
                <label className="field">
                  <span>Email</span>
                  <input type="text" value={registerFields.email} readOnly />
                </label>
                <label className="field">
                  <span>OTP Code</span>
                  <input
                    type="text"
                    value={registerFields.otp}
                    onChange={(event) =>
                      setRegisterFields({ ...registerFields, otp: event.target.value })
                    }
                  />
                  {registerErrors.otp ? (
                    <span className="field-error">{registerErrors.otp}</span>
                  ) : null}
                </label>
                {import.meta.env.DEV && devOtp ? (
                  <div className="dev-banner">DEV OTP (for testing): {devOtp}</div>
                ) : null}
                {otpCountdown ? <p className="muted">Expires in: {otpCountdown}</p> : null}
                <div className="button-row">
                  <Button type="submit" disabled={isSubmitting}>
                    {isSubmitting ? "Verifying..." : "Verify OTP"}
                  </Button>
                  <Button type="button" variant="secondary" disabled={isSubmitting} onClick={handleResendOtpRegister}>
                    Resend OTP
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={isSubmitting}
                    onClick={() => {
                      resetMessages();
                      setRegisterStep("request");
                      setRegisterFields({ ...registerFields, otp: "" });
                      setDevOtp(null);
                      setOtpExpiresAt(null);
                    }}
                  >
                    Back
                  </Button>
                </div>
              </>
            )}
          </form>
        )}
      </Card>
    </section>
  );
}

export default AuthPage;
