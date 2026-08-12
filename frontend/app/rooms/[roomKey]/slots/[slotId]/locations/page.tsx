import LocationsClient from "./locations-client";

export default async function LocationsPage({ params }: { params: Promise<{ roomKey: string; slotId: string }> }) {
  const resolved = await params;
  return <LocationsClient roomKey={resolved.roomKey} slotId={Number(resolved.slotId)} />;
}
