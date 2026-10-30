import { Navigate, type RouteObject } from 'react-router'

import { DocumentsPage } from '@/pages/DocumentsPage'
import { LoginPage } from '@/pages/LoginPage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { RegisterPage } from '@/pages/RegisterPage'

import { GuestOnly, RequireAuth } from './guards'
import { AppLayout, AuthLayout } from './layouts'

export const routes: RouteObject[] = [
  {
    element: <GuestOnly />,
    children: [
      {
        element: <AuthLayout />,
        children: [
          { path: '/login', element: <LoginPage /> },
          { path: '/register', element: <RegisterPage /> },
        ],
      },
    ],
  },
  {
    element: <RequireAuth />,
    children: [
      { element: <AppLayout />, children: [{ path: '/documents', element: <DocumentsPage /> }] },
    ],
  },
  { path: '/', element: <Navigate to="/documents" replace /> },
  { path: '*', element: <NotFoundPage /> },
]
