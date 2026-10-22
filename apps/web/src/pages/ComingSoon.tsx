import { EmptyState } from "../design";

/** A page from a later step of the build. */
export function ComingSoon({ title }: { title: string }) {
  return <EmptyState title={title} description="This page is part of a later step of the build." />;
}
