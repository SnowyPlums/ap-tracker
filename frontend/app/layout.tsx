import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Archipelago Tracker",
  description: "Track Archipelago rooms and players",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><script src="/config.js" />{children}</body></html>;
}
