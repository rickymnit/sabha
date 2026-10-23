// The app's routes (P6.2). Everything except /login needs a session. Pages that are not built yet have no route
// (and no menu entry, app/nav.ts); their addresses show the not-found page.

import { Navigate, type RouteObject } from "react-router-dom";

import { LoginPage } from "../pages/LoginPage";
import { NotFoundPage } from "../pages/NotFoundPage";
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
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
  },
];
