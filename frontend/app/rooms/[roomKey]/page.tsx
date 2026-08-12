import RoomClient from "./room-client";

export default async function RoomPage({ params }: { params: Promise<{ roomKey: string }> }) {
  const { roomKey } = await params;
  return <RoomClient roomKey={roomKey} />;
}
