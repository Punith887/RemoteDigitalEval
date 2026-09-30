import type { Metadata } from "next";
import { Manrope, Source_Sans_3 } from "next/font/google";
import "./globals.css";

const display = Manrope({ subsets: ["latin"], variable: "--font-display" });
const body = Source_Sans_3({ subsets: ["latin"], variable: "--font-body" });

export const metadata: Metadata = {
  title: "ADMIEZO | Evaluation Operations",
  description: "University digital evaluation operations platform",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              if (typeof window !== "undefined") {
                if (!window.crypto) window.crypto = {};
                if (typeof window.crypto.randomUUID !== "function") {
                  window.crypto.randomUUID = function() {
                    return "10000000-1000-4000-8000-100000000000".replace(/[018]/g, function(c) {
                      return (c ^ (Math.random() * 16 >> (c / 4))).toString(16);
                    });
                  };
                }
              }
            `,
          }}
        />
      </head>
      <body className={`${display.variable} ${body.variable}`}>{children}</body>
    </html>
  );
}
