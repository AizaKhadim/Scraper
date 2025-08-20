// Import the functions you need from the SDKs you need
import { initializeApp } from "firebase/app";
import { getAnalytics } from "firebase/analytics";
// TODO: Add SDKs for Firebase products that you want to use
// https://firebase.google.com/docs/web/setup#available-libraries

// Your web app's Firebase configuration
// For Firebase JS SDK v7.20.0 and later, measurementId is optional
const firebaseConfig = {
  apiKey: "AIzaSyCkcZivTkb9eLsHQGpznEuMpM63N0MMu2w",
  authDomain: "scraper-27a0e.firebaseapp.com",
  projectId: "scraper-27a0e",
  storageBucket: "scraper-27a0e.firebasestorage.app",
  messagingSenderId: "279232622634",
  appId: "1:279232622634:web:c1339e05ad83a8c94e5353",
  measurementId: "G-DBG83X6TT9"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const analytics = getAnalytics(app);