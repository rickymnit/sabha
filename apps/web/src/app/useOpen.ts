import { type MouseEvent } from "react";
import { useNavigate } from "react-router-dom";

/** A link handler that stays in the app; a click with a modifier key opens a new tab as usual. */
export function useOpen() {
  const navigate = useNavigate();
  return (event: MouseEvent<HTMLAnchorElement>, to: string) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    navigate(to);
  };
}
