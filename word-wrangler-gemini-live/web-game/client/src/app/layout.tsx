import { Nunito } from 'next/font/google';
import { Metadata } from 'next';
import { Providers } from './providers';
import '../styles/globals.css';

const nunito = Nunito({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-sans',
});

export const metadata: Metadata = {
  title: 'Daily | Word Wrangler',
  description: 'Describe words without saying them and an AI will guess them!',
  icons: {
    icon: [
      { url: '/favicon.ico' },
      { url: '/favicon.svg', type: 'image/svg+xml' },
    ],
  },
  openGraph: {
    type: 'website',
    url: 'https://word-wrangler.vercel.app/',
    title: 'Word Wrangler - AI Word Guessing Game',
    description:
      'Describe words without saying them and an AI will guess them!',
    images: ['/og-image.png'],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Word Wrangler - AI Word Guessing Game',
    description:
      'Describe words without saying them and an AI will guess them!',
    images: ['/og-image.png'],
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <main className={`${nunito.variable}`}>
          <Providers>{children}</Providers>
        </main>
      </body>
    </html>
  );
}
