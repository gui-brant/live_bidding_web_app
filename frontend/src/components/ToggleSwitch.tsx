type ToggleSwitchProps = {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
};

const ToggleSwitch = ({ label, checked, onChange, disabled }: ToggleSwitchProps) => {
  return (
    <label className={`toggle ${disabled ? "disabled" : ""}`.trim()}>
      <span>{label}</span>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        disabled={disabled}
      />
      <span className="toggle-track">
        <span className="toggle-thumb" />
      </span>
    </label>
  );
};

export default ToggleSwitch;

