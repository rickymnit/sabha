// The app's routes (P6.2). Everything except /login needs a session. Pages that are not built yet have no route
// (and no menu entry, app/nav.ts); their addresses show the not-found page.

import { type RouteObject } from "react-router-dom";

import { LoginPage } from "../pages/LoginPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { OverviewRoute } from "../pages/OverviewRoute";
import { PeoplePage } from "../pages/PeoplePage";
import { ReviewPage } from "../pages/ReviewPage";
import { ReviewQueuePage } from "../pages/ReviewQueuePage";
import { SettingsPage } from "../pages/SettingsPage";
import { RecordingPage } from "../pages/RecordingPage";
import { RecordingsPage } from "../pages/RecordingsPage";
import { UploadPage } from "../pages/UploadPage";
import { Home } from "./Home";
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
          { path: "/", element: <Home /> },
          { path: "/overview", element: <OverviewRoute /> },
          { path: "/recordings", element: <RecordingsPage /> },
          { path: "/recordings/:id", element: <RecordingPage /> },
          { path: "/upload", element: <UploadPage /> },
          { path: "/people", element: <PeoplePage /> },
          { path: "/reviews", element: <ReviewQueuePage /> },
          { path: "/reviews/:id", element: <ReviewPage /> },
          { path: "/settings", element: <SettingsPage /> },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
  },
];
