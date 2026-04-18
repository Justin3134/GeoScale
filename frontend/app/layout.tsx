import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'GeoScale',
  description: 'Autonomous local market operator. One goal, full GTM execution.',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className="bg-neutral-950 text-neutral-100 min-h-screen antialiased">
        {children}
      </body>
    </html>
  )
}
