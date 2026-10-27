// The app's routes (P6.2). Everything except /login needs a session. Pages that are not built yet have no route
// (and no menu entry, app/nav.ts); their addresses show the not-found page.

import { type RouteObject } from "react-router-dom";

import { LoginPage } from "../pages/LoginPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { AppLoading } from "./AppLoading";
import { Home } from "./Home";
import { Layout } from "./Layout";
import { ADMINS, RESOLVERS } from "./nav";
import { RequireSession } from "./RequireSession";
import { RoleGate } from "./RoleGate";

// Pages load when first opened (P6.8), so the first screen needs only the shell. While a page loads, the one before
// stays on screen; on the very first load, AppLoading shows.
const page = (load: () => Promise<{ Component: RouteObject["Component"] }>): Pick<RouteObject, "lazy"> => ({
  lazy: load,
});

export const routes: RouteObject[] = [
  { path: "/login", element: <LoginPage /> },
  {
    element: <RequireSession />,
    hydrateFallbackElement: <AppLoading />,
    children: [
      {
        element: <Layout />,
        children: [
          { path: "/", element: <Home /> },
          {
            // Owners, admins, managers and reviewers: staff have no overview, people list or review queue.
            element: <RoleGate roles={RESOLVERS} />,
            children: [
              {
                path: "/overview",
                ...page(() => import("../pages/OverviewRoute").then((m) => ({ Component: m.OverviewRoute }))),
              },
              {
                path: "/people",
                ...page(() => import("../pages/PeoplePage").then((m) => ({ Component: m.PeoplePage }))),
              },
              {
                path: "/reviews",
                ...page(() => import("../pages/ReviewQueuePage").then((m) => ({ Component: m.ReviewQueuePage }))),
              },
              {
                path: "/reviews/:id",
                ...page(() => import("../pages/ReviewPage").then((m) => ({ Component: m.ReviewPage }))),
              },
            ],
          },
          {
            path: "/recordings",
            ...page(() => import("../pages/RecordingsPage").then((m) => ({ Component: m.RecordingsPage }))),
          },
          {
            path: "/recordings/:id",
            ...page(() => import("../pages/RecordingPage").then((m) => ({ Component: m.RecordingPage }))),
          },
          { path: "/upload", ...page(() => import("../pages/UploadPage").then((m) => ({ Component: m.UploadPage }))) },
          {
            path: "/rubrics",
            ...page(() => import("../pages/RubricsPage").then((m) => ({ Component: m.RubricsPage }))),
          },
          {
            path: "/rubrics/:id",
            ...page(() => import("../pages/RubricsPage").then((m) => ({ Component: m.RubricsPage }))),
          },
          {
            // Owners and admins: the audit log (P1.8).
            element: <RoleGate roles={ADMINS} />,
            children: [
              {
                path: "/activity",
                ...page(() => import("../pages/ActivityPage").then((m) => ({ Component: m.ActivityPage }))),
              },
            ],
          },
          {
            path: "/settings",
            ...page(() => import("../pages/SettingsPage").then((m) => ({ Component: m.SettingsPage }))),
          },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
  },
];
