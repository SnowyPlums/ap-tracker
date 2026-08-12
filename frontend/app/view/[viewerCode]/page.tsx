import ViewerClient from "./viewer-client";

export default async function ViewerPage({ params }: { params: Promise<{ viewerCode: string }> }) {
  const { viewerCode } = await params;
  return <ViewerClient viewerCode={viewerCode} />;
}
