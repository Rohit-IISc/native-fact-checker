import { type Firestore, getFirestore } from 'firebase/firestore'
import { config } from './config'
import { firebaseApp } from './firebase'

/** Firestore lives in its own module so only the live check screen loads it (smaller first page). */
export function db(): Firestore {
  return getFirestore(firebaseApp(), config.firestoreDb)
}
