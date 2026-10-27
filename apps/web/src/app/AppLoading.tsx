// The full-screen loading state: the logo over two skeleton lines (P6.2). Shown while the first page's code loads
// (app/routes.tsx) and while the signed-in workspace loads (app/Layout.tsx).

import { Logo, Skeleton, SkeletonGroup } from "../design";

export function AppLoading({ label = "Loading Sabha" }: { label?: string }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-page">
      <Logo size={40} />
      <SkeletonGroup label={label} className="flex w-64 flex-col gap-2">
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-3 w-2/3" />
      </SkeletonGroup>
    </div>
  );
}
