// The app's routes (P6.2). Everything except /login needs a session; pages from later steps are placeholders.

import { Navigate, type RouteObject } from "react-router-dom";

import { ComingSoon } from "../pages/ComingSoon";
import { LoginPage } from "../pages/LoginPage";
import { RecordingPage } from "../pages/RecordingPage";
import { RecordingsPage } from "../pages/RecordingsPage";
import { UploadPage } from "../pages/UploadPage";
import { Layout } from "./Layout";
import { RequireSession } from "./RequireSession";

export const routes: RouteObject[] = [
  { path: "/login", element: <LoginPage /> },
  {
    element: <RequireSession />,
    children: [
      {
        element: <Layout />,
        children: [
          { path: "/", element: <Navigate to="/recordings" replace /> },
          { path: "/recordings", element: <RecordingsPage /> },
          { path: "/recordings/:id", element: <RecordingPage /> },
          { path: "/upload", element: <UploadPage /> },
          { path: "/people", element: <ComingSoon title="People" /> },
          { path: "/reviews", element: <ComingSoon title="Reviews" /> },
          { path: "/rubrics", element: <ComingSoon title="Rubrics" /> },
          { path: "/settings", element: <ComingSoon title="Settings" /> },
          { path: "*", element: <ComingSoon title="Page not found" /> },
        ],
      },
    ],
  },
];
