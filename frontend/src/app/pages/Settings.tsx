import { useEffect, useState } from "react";

import { api } from "../../api";
import type { NotificationPreferences } from "../../api/types";
import Button from "../../components/Button";
import Card from "../../components/Card";
import Spinner from "../../components/Spinner";
import ToggleSwitch from "../../components/ToggleSwitch";

const Settings = () => {
  const [prefs, setPrefs] = useState<NotificationPreferences | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "light");
  const [layout, setLayout] = useState(() => localStorage.getItem("rep_bidding_layout") || "classic");

  useEffect(() => {
    const loadPrefs = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const response = await api.prefs.get();
        setPrefs(response);
      } catch (err) {
        console.error(err);
        setError("Failed to load preferences.");
      } finally {
        setIsLoading(false);
      }
    };

    void loadPrefs();
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
  }, [theme]);

  const updateField = (field: keyof NotificationPreferences, value: boolean) => {
    if (!prefs) {
      return;
    }
    setPrefs({ ...prefs, [field]: value });
  };

  const handleSave = async () => {
    if (!prefs) {
      return;
    }

    setIsSaving(true);
    setError(null);
    setMessage(null);

    try {
      const response = await api.prefs.update(prefs);
      setPrefs(response);
      setMessage("Preferences saved.");
    } catch (err) {
      console.error(err);
      setError("Failed to save preferences.");
    } finally {
      setIsSaving(false);
    }
  };

  const handleLayoutChange = (value: string) => {
    setLayout(value);
    localStorage.setItem("rep_bidding_layout", value);
    setMessage("Bidding room layout updated.");
  };

  const handleThemeChange = (value: boolean) => {
    setTheme(value ? "dark" : "light");
  };

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1>Settings</h1>
          <p className="muted">Manage how you receive notifications.</p>
        </div>
      </div>

      {isLoading ? (
        <div className="center">
          <Spinner />
        </div>
      ) : null}

      {error ? <p className="error">{error}</p> : null}
      {message ? <p className="success">{message}</p> : null}

      <Card className="settings-card">
        {prefs ? (
          <div className="settings-stack">
            <div className="settings-section">
              <h3>Appearance</h3>
              <div className="settings-row">
                <span>Dark mode</span>
                <ToggleSwitch label="" checked={theme === "dark"} onChange={handleThemeChange} />
              </div>
            </div>

            <div className="settings-divider" />

            <div className="settings-section">
              <h3>Notification Preferences</h3>
              <div className="settings-row">
                <span>In-app</span>
                <ToggleSwitch
                  label=""
                  checked={prefs.enable_in_app}
                  onChange={(value) => updateField("enable_in_app", value)}
                />
              </div>
              <div className="settings-row">
                <span>Email</span>
                <ToggleSwitch
                  label=""
                  checked={prefs.enable_email}
                  onChange={(value) => updateField("enable_email", value)}
                />
              </div>
            </div>

            <div className="settings-divider" />

            <div className="settings-section">
              <h3>Auction Alerts</h3>
              <div className="settings-row">
                <span>Notify when outbid</span>
                <ToggleSwitch
                  label=""
                  checked={prefs.notify_outbid}
                  onChange={(value) => updateField("notify_outbid", value)}
                />
              </div>
              <div className="settings-row">
                <span>Auction time frame updates</span>
                <ToggleSwitch
                  label=""
                  checked={prefs.notify_auction_timeframe}
                  onChange={(value) => updateField("notify_auction_timeframe", value)}
                />
              </div>
              <div className="settings-row">
                <span>Notify when you win</span>
                <ToggleSwitch
                  label=""
                  checked={prefs.notify_auction_win}
                  onChange={(value) => updateField("notify_auction_win", value)}
                />
              </div>
            </div>

            <Button type="button" className="settings-save" onClick={handleSave} disabled={isSaving}>
              {isSaving ? "Saving..." : "Save"}
            </Button>
          </div>
        ) : null}
      </Card>

      <Card title="Bidding Room Layout" className="settings-card settings-layout-card">
        <div className="form">
          <label className="field">
            <span>Layout</span>
            <select value={layout} onChange={(event) => handleLayoutChange(event.target.value)}>
              <option value="classic">Classic (stacked)</option>
              <option value="split">Split (items right)</option>
              <option value="focus">Focus (items top)</option>
            </select>
          </label>
          <p className="muted">Applies to the rep bidding room. Refresh if the room is already open.</p>
        </div>
      </Card>

    </section>
  );
};

export default Settings;
