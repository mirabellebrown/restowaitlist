import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RestoWaitlist — Better timing for dinner",
  description:
    "Track public restaurant wait estimates and choose a smarter time to join.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
