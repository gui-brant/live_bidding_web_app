import type { ButtonHTMLAttributes } from "react";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary";
};

const Button = ({ variant = "primary", className = "", ...props }: ButtonProps) => {
  return <button className={`btn ${variant} ${className}`.trim()} {...props} />;
};

export default Button;

